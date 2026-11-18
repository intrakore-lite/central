import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { runInNewContext } from 'node:vm'
import typescript from 'typescript'

// brand.ts reads the boot data from window at import, so each case compiles it with its own.
function loadBrand(window) {
	const source = readFileSync(
		new URL('../src/lib/brand.ts', import.meta.url),
		'utf8',
	)
	const compiled = typescript.transpileModule(source, {
		compilerOptions: { module: typescript.ModuleKind.CommonJS },
	}).outputText
	const exports = {}
	runInNewContext(compiled, {
		exports,
		require: (name) => ({ default: name }),
		window,
	})
	return exports
}

const DEFAULT_LINE = 'Trusted by 500+ construction customers across the UAE'

test('the auth pages keep the default line when the boot has none', () => {
	assert.equal(loadBrand({}).trustLine, DEFAULT_LINE)
})

test('the auth pages show the trust line from Central Settings', () => {
	const { trustLine } = loadBrand({
		auth_trust_line: ' Hosted in Frankfurt, EU\nISO 9001 ',
	})
	assert.equal(trustLine, 'Hosted in Frankfurt, EU\nISO 9001')
})

test('an empty or null trust line hides the line', () => {
	assert.equal(loadBrand({ auth_trust_line: null }).trustLine, null)
	assert.equal(loadBrand({ auth_trust_line: '  ' }).trustLine, null)
})
