import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { runInNewContext } from 'node:vm'
import typescript from 'typescript'
import { computed, ref } from 'vue'

const image = (id, version, created_at, tags = {}, architecture = 'arm64') => ({
	id,
	title: id,
	architecture,
	created_at,
	rootfs_size_mib: 1024,
	tags: { frappe_version: version, has_site: '0', ...tags },
})

function loadRegionalImages(responses) {
	const api = {
		listImageOfferings: 'offerings',
		listRegionalImages: 'images',
		listServerProducts: 'products',
	}
	const dependencies = {
		vue: { computed, ref, watch: () => {} },
		'frappe-ui': { frappeRequest: async ({ url }) => responses[url] },
		'@/api/methods': { API: api, methodV1: (value) => value },
		'@/composables/useSession': {
			useSession: () => ({ activeTeam: ref('team') }),
		},
		'@/lib/feedback': { getErrorMessage: String },
		'@/lib/format': { formatUnixTime: String },
	}
	const source = readFileSync(
		new URL('../src/composables/useRegionalImages.ts', import.meta.url),
		'utf8',
	)
	const exports = {}
	runInNewContext(
		typescript.transpileModule(source, {
			compilerOptions: { module: typescript.ModuleKind.CommonJS },
		}).outputText,
		{ exports, require: (name) => dependencies[name] },
	)
	return exports.useRegionalImages(ref('region'))
}

test('server choices exclude site builds and retain the newest base build per version and architecture', async () => {
	const images = [
		image('old', 'version-16', 1),
		image('new', 'version-16', 2),
		image('site', 'version-16', 3, { has_site: '1' }),
		image('app', 'version-16', 4, { app: 'crm' }),
		image('untagged', 'version-16', 5, { has_site: undefined }),
		image('nightly', 'develop', 6),
		image('amd', 'version-16', 7, {}, 'amd64'),
	]
	const choices = loadRegionalImages({
		offerings: [{ name: 'frappe' }],
		products: [],
		images: { items: images, next_offset: null },
	})
	choices.offering.value = 'frappe'
	await choices.reload()
	assert.equal(choices.error.value, '')
	assert.deepEqual(
		Array.from(choices.imageOptions.value.slice(1), (row) => row.value).sort(),
		['amd', 'new', 'nightly'],
	)
	assert.equal(choices.imageId.value, 'amd')
})

test('a product is a choice that selects its image and names itself to Central', async () => {
	const crm = {
		name: 'crm',
		title: 'CRM + Estimation',
		logo: null,
		description: 'Sales to estimate',
		offering: 'pilot',
		image_id: 'crm-image',
	}
	const choices = loadRegionalImages({
		offerings: [{ name: 'ubuntu', title: 'Ubuntu' }],
		products: [crm],
	})
	await choices.reload()
	assert.deepEqual(
		Array.from(choices.offerings.value, (row) => row.name),
		['product:crm', 'ubuntu'],
	)
	assert.equal(choices.offering.value, 'product:crm')

	await choices.reload()
	assert.equal(choices.error.value, '')
	assert.equal(choices.product.value?.name, 'crm')
	assert.equal(choices.imageId.value, 'crm-image')
	assert.equal(
		JSON.stringify(choices.selection.value),
		JSON.stringify({
			offering: 'pilot',
			image_id: 'crm-image',
			product: 'crm',
		}),
	)
})
