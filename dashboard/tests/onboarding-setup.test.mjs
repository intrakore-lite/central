import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { runInNewContext } from 'node:vm'
import typescript from 'typescript'

function load(path) {
	const source = readFileSync(new URL(path, import.meta.url), 'utf8')
	const exports = {}
	runInNewContext(
		typescript.transpileModule(source, {
			compilerOptions: { module: typescript.ModuleKind.CommonJS },
		}).outputText,
		{ exports },
	)
	return exports
}

// The modules run in their own realm, so their arrays and objects are compared as plain JSON.
const plain = (value) => JSON.parse(JSON.stringify(value))

const invites = load('../src/lib/teamInvites.ts')
const setup = load('../src/lib/masterSetup.ts')
const steps = load('../src/components/onboarding/setup/steps.ts')

test('a CSV with a header imports its members', () => {
	const { rows, errors } = invites.parseMembersCsv(
		'﻿name,email,modules,role\r\n' +
			'Layla Al-Hassan,Layla@Example.com,both,Estimator\r\n' +
			'"Mansour, Tariq",tariq@example.com,CRM only,sales manager\r\n',
	)
	assert.equal(errors.length, 0)
	assert.equal(rows.length, 2)
	assert.deepEqual(plain(rows[0]), {
		full_name: 'Layla Al-Hassan',
		email: 'layla@example.com',
		modules: 'both',
		role: 'Estimator',
	})
	assert.equal(rows[1].full_name, 'Mansour, Tariq')
	assert.equal(rows[1].modules, 'crm')
	assert.equal(rows[1].role, 'Sales Manager')
})

test('a CSV line without modules or role gets both and Estimator', () => {
	const { rows } = invites.parseMembersCsv('Ali,ali@example.com')
	assert.equal(rows[0].modules, 'both')
	assert.equal(rows[0].role, 'Estimator')
})

test('bad CSV lines are reported and repeated emails imported once', () => {
	const { rows, errors } = invites.parseMembersCsv(
		[
			'A,a@example.com,crm,Admin',
			'B,not-an-email,crm,Admin',
			'C,c@example.com,hr,Admin',
			'D,d@example.com,crm,Owner',
			'A again,A@example.com,both,Estimator',
		].join('\n'),
	)
	assert.equal(rows.length, 1)
	assert.deepEqual(plain(errors.map((error) => error.split(':')[0])), [
		'Line 2',
		'Line 3',
		'Line 4',
	])
})

test('a CSV of more than 200 members is cut to the site limit', () => {
	const lines = Array.from(
		{ length: 205 },
		(_, index) => `M${index},m${index}@example.com`,
	)
	const { rows, errors } = invites.parseMembersCsv(lines.join('\n'))
	assert.equal(rows.length, invites.MAX_INVITES)
	assert.match(errors.at(-1), /first 200/)
})

test('a row needs a valid email that is not the owner', () => {
	const row = { ...invites.emptyRow(), email: 'Owner@Example.com' }
	assert.equal(invites.rowError(invites.emptyRow()), 'Enter a work email.')
	assert.equal(
		invites.rowError({ ...row, email: 'nope' }),
		'Enter a valid work email.',
	)
	assert.equal(
		invites.rowError(row, 'owner@example.com'),
		'You are already the owner.',
	)
	assert.equal(invites.rowError({ ...row, email: 'x@example.com' }), '')
	assert.deepEqual(
		[
			...invites.duplicateEmails([
				{ ...row, email: 'a@x.com' },
				{ ...row, email: ' A@x.com ' },
				{ ...row, email: 'b@x.com' },
			]),
		],
		['a@x.com'],
	)
})

test('seat share is capped at 100 and zero without a cap', () => {
	assert.equal(invites.seatShare(3, 15), 20)
	assert.equal(invites.seatShare(20, 15), 100)
	assert.equal(invites.seatShare(3, null), 0)
})

test('setting one weight shares the rest so the total stays 100', () => {
	const start = { solvency: 35, margin_risk: 40, capacity: 25 }
	const next = setup.rebalanceWeights(start, 'solvency', 50)
	assert.equal(next.solvency, 50)
	assert.equal(setup.weightTotal(next), 100)
	// The others keep their 40:25 proportion.
	assert.ok(next.margin_risk > next.capacity)

	for (const value of [0, 1, 33, 99, 100, 140, -5]) {
		const weights = setup.rebalanceWeights(start, 'capacity', value)
		assert.equal(setup.weightTotal(weights), 100, `value ${value}`)
		assert.ok(Object.values(weights).every(Number.isInteger))
	}
})

test('when the other weights are zero the rest is shared equally', () => {
	const next = setup.rebalanceWeights(
		{ solvency: 100, margin_risk: 0, capacity: 0 },
		'solvency',
		40,
	)
	assert.deepEqual(plain(next), { solvency: 40, margin_risk: 30, capacity: 30 })
})

test('the GCC preset is valid and the toggle recognises it', () => {
	const form = setup.cloneSetup(setup.GCC_PRESET)
	assert.equal(setup.setupErrors(form).length, 0)
	assert.ok(setup.matchesPreset(form, setup.GCC_PRESET))
	form.lead_sources.reverse()
	assert.ok(setup.matchesPreset(form, setup.GCC_PRESET))
	form.overhead_pct = 9
	assert.ok(!setup.matchesPreset(form, setup.GCC_PRESET))
	assert.equal(setup.GCC_PRESET.overhead_pct, 8, 'clone does not share state')
	assert.equal(setup.weightTotal(setup.NEUTRAL_SETUP.bid_weights), 100)
})

test('the form becomes the config the site API takes', () => {
	const config = setup.toMasterConfig(setup.GCC_PRESET)
	assert.deepEqual(plain(Object.keys(config.crm).sort()), [
		'bid_weights',
		'deal_currency',
		'lead_sources',
		'pipeline_stages',
		'threshold',
	])
	assert.deepEqual(plain(config.estimation.templates), ['general_civil'])
	assert.equal(config.estimation.uom_system, 'metric')
	assert.equal(config.crm.deal_currency, 'AED')
})

test('every template key matches the starter content keys', () => {
	assert.deepEqual(plain(setup.TEMPLATES.map((template) => template.key)), [
		'general_civil',
		'mep',
		'fitout_interior',
		'heavy_infrastructure',
		'villa',
		'restaurant',
		'office',
	])
})

test('weights that do not add up and bad percentages are refused', () => {
	const form = setup.cloneSetup(setup.GCC_PRESET)
	form.bid_weights.capacity = 30
	form.net_margin_pct = 120
	assert.equal(setup.setupErrors(form).length, 2)
})

test('moving a milestone keeps the others in order', () => {
	assert.deepEqual(plain(setup.moveItem(['a', 'b', 'c', 'd'], 0, 2)), [
		'b',
		'c',
		'a',
		'd',
	])
	assert.deepEqual(plain(setup.moveItem(['a', 'b'], 1, 9)), ['a', 'b'])
	assert.deepEqual(plain(setup.moveItem(['a', 'b'], 5, 0)), ['a', 'b'])
})

test('a returning owner resumes at the right step', () => {
	assert.equal(steps.resumeRedirect(3, 5), '/servers')
	assert.equal(steps.resumeRedirect(4, 2), '/onboarding/billing')
	assert.equal(steps.resumeRedirect(1, 4), '/onboarding/modules-setup')
	assert.equal(steps.resumeRedirect(2, 2), null)
	assert.equal(steps.resumeRedirect(1, 2), null, 'step 1 stays editable')
	assert.equal(steps.resumeRedirect(3, 4), null, 'step 3 can be revisited')
	assert.equal(steps.resumeRedirect(4, 4), null)
})
