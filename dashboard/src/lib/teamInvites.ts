// Onboarding step 3: the rows of the team invitation form, and the CSV import.
// No imports, so the node tests run this file as it is.

export type ModuleAccess = 'crm' | 'estimation' | 'both'
export type MemberRole = 'Admin' | 'Estimator' | 'Sales Rep' | 'Sales Manager'

export const MODULE_OPTIONS: { value: ModuleAccess; label: string }[] = [
	{ value: 'crm', label: 'CRM only' },
	{ value: 'estimation', label: 'Estimation only' },
	{ value: 'both', label: 'Both Modules' },
]

export const ROLE_OPTIONS: MemberRole[] = [
	'Admin',
	'Estimator',
	'Sales Rep',
	'Sales Manager',
]

/** The most rows the site takes in one call. */
export const MAX_INVITES = 200

export interface InviteRow {
	full_name: string
	email: string
	modules: ModuleAccess
	role: MemberRole
}

export interface CsvImport {
	rows: InviteRow[]
	/** One line per refused CSV line, such as "Line 3: enter a valid email." */
	errors: string[]
}

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const MODULE_ALIASES: Record<string, ModuleAccess> = {
	crm: 'crm',
	'crm only': 'crm',
	estimation: 'estimation',
	'estimation only': 'estimation',
	both: 'both',
	'both modules': 'both',
	'crm+estimation': 'both',
	'crm & estimation': 'both',
}

export function isValidEmail(value: string): boolean {
	return EMAIL.test(value.trim())
}

export function emptyRow(): InviteRow {
	return { full_name: '', email: '', modules: 'both', role: 'Estimator' }
}

/** A row the owner has started to fill in. Untouched rows are left out of a bulk send. */
export function isBlankRow(row: InviteRow): boolean {
	return !row.full_name.trim() && !row.email.trim()
}

/** Why a row cannot be sent yet, or an empty string. */
export function rowError(row: InviteRow, ownerEmail = ''): string {
	const email = row.email.trim().toLowerCase()
	if (!email) return 'Enter a work email.'
	if (!isValidEmail(email)) return 'Enter a valid work email.'
	if (ownerEmail && email === ownerEmail.toLowerCase())
		return 'You are already the owner.'
	return ''
}

/** The email addresses that appear in more than one row, lower-cased. */
export function duplicateEmails(rows: InviteRow[]): Set<string> {
	const seen = new Set<string>()
	const duplicates = new Set<string>()
	for (const row of rows) {
		const email = row.email.trim().toLowerCase()
		if (!email) continue
		if (seen.has(email)) duplicates.add(email)
		seen.add(email)
	}
	return duplicates
}

export function parseModules(value: string): ModuleAccess | null {
	return MODULE_ALIASES[value.trim().toLowerCase()] ?? null
}

export function parseRole(value: string): MemberRole | null {
	const wanted = value.trim().toLowerCase()
	return ROLE_OPTIONS.find((role) => role.toLowerCase() === wanted) ?? null
}

/** Split one CSV line, honouring double quotes and doubled quotes inside them. */
export function splitCsvLine(line: string): string[] {
	const cells: string[] = []
	let cell = ''
	let quoted = false
	for (let index = 0; index < line.length; index++) {
		const char = line[index]
		if (quoted) {
			if (char === '"' && line[index + 1] === '"') {
				cell += '"'
				index++
			} else if (char === '"') quoted = false
			else cell += char
		} else if (char === '"') quoted = true
		else if (char === ',' || char === ';') {
			cells.push(cell)
			cell = ''
		} else cell += char
	}
	cells.push(cell)
	return cells.map((value) => value.trim())
}

/**
 * Read `name,email,modules,role` lines. A header line is skipped. An empty module
 * means both, and an empty role means Estimator. Bad lines are reported, not
 * imported, and an email that repeats is imported once.
 */
export function parseMembersCsv(text: string): CsvImport {
	const rows: InviteRow[] = []
	const errors: string[] = []
	const seen = new Set<string>()
	const lines = text.replace(/^﻿/, '').split(/\r?\n/)

	lines.forEach((line, index) => {
		const number = index + 1
		if (!line.trim()) return
		const [name = '', email = '', modules = '', role = ''] = splitCsvLine(line)
		if (index === 0 && !isValidEmail(email) && /e-?mail/i.test(email)) return

		const address = email.toLowerCase()
		if (!isValidEmail(address)) {
			errors.push(`Line ${number}: enter a valid email.`)
			return
		}
		const access = modules ? parseModules(modules) : 'both'
		if (!access) {
			errors.push(`Line ${number}: modules must be crm, estimation or both.`)
			return
		}
		const memberRole = role ? parseRole(role) : 'Estimator'
		if (!memberRole) {
			errors.push(
				`Line ${number}: role must be one of ${ROLE_OPTIONS.join(', ')}.`,
			)
			return
		}
		if (seen.has(address)) return
		seen.add(address)
		rows.push({
			full_name: name,
			email: address,
			modules: access,
			role: memberRole,
		})
	})

	if (rows.length > MAX_INVITES) {
		errors.push(`Only the first ${MAX_INVITES} members were imported.`)
		rows.length = MAX_INVITES
	}
	return { rows, errors }
}

/** The CSV the template link downloads. */
export const CSV_TEMPLATE =
	'name,email,modules,role\nLayla Al-Hassan,layla@example.com,both,Estimator\n'

/** Seats in use as a share of the cap, from 0 to 100. */
export function seatShare(used: number, cap: number | null): number {
	if (!cap || cap <= 0) return 0
	return Math.min(100, Math.round((used / cap) * 100))
}
