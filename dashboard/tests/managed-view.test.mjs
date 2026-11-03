import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { runInNewContext } from 'node:vm'
import typescript from 'typescript'

const source = readFileSync(
	new URL('../src/lib/managedView.ts', import.meta.url),
	'utf8',
)
const exports = {}
runInNewContext(
	typescript.transpileModule(source, {
		compilerOptions: { module: typescript.ModuleKind.CommonJS },
	}).outputText,
	{ exports, URL },
)
const {
	customerLine,
	planName,
	seatsLabel,
	siteAddress,
	siteFacts,
	teamSeats,
} = exports

test('a site address is https and the host only, from a URL or a bare hostname', () => {
	assert.equal(
		siteAddress('https://acme.intrakore.cloud/'),
		'https://acme.intrakore.cloud',
	)
	assert.equal(
		siteAddress('http://acme.intrakore.cloud/app/home'),
		'https://acme.intrakore.cloud',
	)
	assert.equal(
		siteAddress('acme.intrakore.cloud'),
		'https://acme.intrakore.cloud',
	)
	assert.equal(siteAddress('  '), '')
	assert.equal(siteAddress(null), '')
	assert.equal(siteAddress('https://'), '')
})

test('a row line is the site address, then the product, then the status', () => {
	const visual = { label: 'Active' }
	assert.equal(
		customerLine({
			site: { url: 'https://acme.intrakore.cloud', name: 'acme' },
			productTitle: 'CRM',
			visual,
		}),
		'https://acme.intrakore.cloud',
	)
	assert.equal(
		customerLine({
			site: { url: null, name: 'acme.intrakore.cloud' },
			visual,
		}),
		'https://acme.intrakore.cloud',
	)
	assert.equal(customerLine({ productTitle: 'CRM', visual }), 'CRM')
	assert.equal(customerLine({ productTitle: '  ', visual }), 'Active')
})

test('a row line never shows specs, an IP address or a region', () => {
	const line = customerLine({
		site: undefined,
		visual: { label: 'Setting up' },
		specs: '4 vCPU, 8 GB RAM, 75 GB Disk',
		regionLabel: 'Mumbai, India',
		server: { public_ipv4: '203.0.113.7', ipv6_address: 'fdaa::1' },
	})
	assert.equal(line, 'Setting up')
})

test('seats are read defensively while the Team field is new', () => {
	assert.equal(teamSeats({ seats: 10 }), 10)
	assert.equal(teamSeats({ seats: '5' }), 5)
	assert.equal(teamSeats({ seats: 0 }), null)
	assert.equal(teamSeats({ seats: 'many' }), null)
	assert.equal(teamSeats({}), null)
	assert.equal(teamSeats(null), null)

	assert.equal(seatsLabel({ members: 3, seats: 10 }), '3 of 10 seats')
	assert.equal(seatsLabel({ members: 1, seats: 1 }), '1 of 1 seat')
	assert.equal(seatsLabel({ members: 3 }), '3 members')
	assert.equal(seatsLabel({ members: 1 }), '1 member')
	assert.equal(seatsLabel({ members: 0 }), null)
	assert.equal(seatsLabel(null), null)
})

test('a plan name drops the size Central appends', () => {
	assert.equal(planName('Starter · 2 vCPU · 4 GB'), 'Starter')
	assert.equal(planName(null), '')
})

test('site facts keep the order and leave out what is unknown', () => {
	const facts = siteFacts({
		siteUrl: 'https://acme.intrakore.cloud',
		productTitle: 'Estimation',
		planTitle: 'Team · 4 vCPU',
		team: { members: 2, seats: 5 },
		storageUsed: '1.2 GB',
		status: 'Active',
	})
	assert.deepEqual(
		[...facts].map((fact) => [fact.key, fact.value]),
		[
			['address', 'https://acme.intrakore.cloud'],
			['product', 'Estimation'],
			['plan', 'Team'],
			['seats', '2 of 5 seats'],
			['storage', '1.2 GB'],
			['status', 'Active'],
		],
	)
	assert.equal(facts[0].href, 'https://acme.intrakore.cloud')

	const bare = siteFacts({ status: 'Stopped' })
	assert.deepEqual(
		[...bare].map((fact) => fact.key),
		['status'],
	)
})
