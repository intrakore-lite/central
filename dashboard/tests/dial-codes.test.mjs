import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { runInNewContext } from 'node:vm'
import typescript from 'typescript'

const source = readFileSync(
	new URL('../src/lib/dialCodes.ts', import.meta.url),
	'utf8',
)
const exports = {}
runInNewContext(
	typescript.transpileModule(source, {
		compilerOptions: { module: typescript.ModuleKind.CommonJS },
	}).outputText,
	{ exports },
)
const { splitMobile, joinMobile, DIAL_CODES } = exports

test('a stored UAE mobile splits into +971 and the local number', () => {
	const { dial, number } = splitMobile('+971508329410')
	assert.equal(dial.code, '+971')
	assert.equal(number, '508329410')
})

test('an unknown or missing code falls back to the UAE', () => {
	assert.equal(splitMobile('').dial.code, '+971')
	assert.equal(splitMobile('+49301234567').dial.code, '+971')
})

test('the local number drops spaces and the trunk zero', () => {
	assert.equal(joinMobile(DIAL_CODES[0], '050 832 9410'), '+971508329410')
	assert.equal(joinMobile(DIAL_CODES[0], '  '), '')
})
