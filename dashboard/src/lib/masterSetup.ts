// Onboarding step 4: the CRM and Estimation master setup, its presets, and the
// bid/no-bid weights. No imports, so the node tests run this file as it is.

export type WeightKey = 'solvency' | 'margin_risk' | 'capacity'
export type Weights = Record<WeightKey, number>
export type UomSystem = 'metric' | 'imperial'
export type TemplateKey =
	| 'general_civil'
	| 'mep'
	| 'fitout_interior'
	| 'heavy_infrastructure'
	| 'villa'
	| 'restaurant'
	| 'office'
export type LabourRateBase = 'gcc_wage_base' | 'own_rates'

export interface MasterSetupForm {
	pipeline_stages: string[]
	deal_currency: string
	bid_weights: Weights
	threshold: number
	lead_sources: string[]
	uom_system: UomSystem
	net_margin_pct: number
	overhead_pct: number
	template: TemplateKey
	labour_rate_base: LabourRateBase
}

/** What central.api.onboarding.apply_master_setup sends to the site. */
export interface MasterSetupConfig {
	crm: {
		lead_sources: string[]
		bid_weights: Weights
		deal_currency: string
		pipeline_stages: string[]
		threshold: number
	}
	estimation: {
		uom_system: UomSystem
		templates: TemplateKey[]
		net_margin_pct: number
		overhead_pct: number
		labour_rate_base: LabourRateBase
	}
}

export const WEIGHT_LABELS: { key: WeightKey; label: string }[] = [
	{ key: 'solvency', label: 'Client Financial Solvency & Escrow' },
	{ key: 'margin_risk', label: 'Project Margin Risk & Complexity' },
	{ key: 'capacity', label: 'Internal Plant & Labor Availability' },
]

export const PIPELINE_STAGES = [
	'Lead In',
	'Tender Received',
	'Bid/No-Bid Review',
	'Estimating',
	'Proposal Submitted',
	'Negotiation',
	'Won / Lost',
]

export const LEAD_SOURCES = [
	'Government Tenders Board',
	'Developer Direct RFP',
	'Partner & JV Referrals',
	'Procurement Portal Direct',
	'Existing Client Repeat',
	'Website Enquiry',
]

export const CURRENCIES = [
	{ code: 'AED', label: 'AED (United Arab Emirates Dirham)' },
	{ code: 'SAR', label: 'SAR (Saudi Riyal)' },
	{ code: 'QAR', label: 'QAR (Qatari Riyal)' },
	{ code: 'KWD', label: 'KWD (Kuwaiti Dinar)' },
	{ code: 'BHD', label: 'BHD (Bahraini Dinar)' },
	{ code: 'OMR', label: 'OMR (Omani Rial)' },
	{ code: 'USD', label: 'USD (US Dollar)' },
	{ code: 'EUR', label: 'EUR (Euro)' },
	{ code: 'GBP', label: 'GBP (Pound Sterling)' },
	{ code: 'INR', label: 'INR (Indian Rupee)' },
]

export const TEMPLATES: {
	key: TemplateKey
	title: string
	text: string
}[] = [
	{
		key: 'general_civil',
		title: 'General Civil Works',
		text: 'POMI / RICS standard structural specs',
	},
	{
		key: 'mep',
		title: 'MEP Services',
		text: 'HVAC, plumbing, LV / ELV distribution',
	},
	{
		key: 'fitout_interior',
		title: 'Fit-out & Interior',
		text: 'Architectural finishes, joinery & FF&E',
	},
	{
		key: 'heavy_infrastructure',
		title: 'Heavy Infrastructure',
		text: 'Earthworks, roads, utilities, drainage',
	},
	{
		key: 'villa',
		title: 'Villa',
		text: 'Residential villas, shell & core to handover',
	},
	{
		key: 'restaurant',
		title: 'Restaurant',
		text: 'F&B fit-out, kitchen MEP and finishes',
	},
	{
		key: 'office',
		title: 'Office',
		text: 'Commercial office fit-out and services',
	},
]

export const LABOUR_RATE_BASES: {
	key: LabourRateBase
	title: string
	text: string
}[] = [
	{
		key: 'gcc_wage_base',
		title: 'GCC construction wage base',
		text: 'Includes visa, accommodation and insurance overhead factors',
	},
	{
		key: 'own_rates',
		title: 'Our own labour and plant rates',
		text: 'Start empty and enter your own rate book',
	},
]

/** The UAE / GCC Presets toggle fills these. */
export const GCC_PRESET: MasterSetupForm = {
	pipeline_stages: [...PIPELINE_STAGES],
	deal_currency: 'AED',
	bid_weights: { solvency: 35, margin_risk: 40, capacity: 25 },
	threshold: 75,
	lead_sources: LEAD_SOURCES.slice(0, 4),
	uom_system: 'metric',
	net_margin_pct: 12,
	overhead_pct: 8,
	template: 'general_civil',
	labour_rate_base: 'gcc_wage_base',
}

/** Turning the presets off returns to these neutral values. */
export const NEUTRAL_SETUP: MasterSetupForm = {
	pipeline_stages: [...PIPELINE_STAGES],
	deal_currency: 'AED',
	bid_weights: { solvency: 34, margin_risk: 33, capacity: 33 },
	threshold: 60,
	lead_sources: [],
	uom_system: 'metric',
	net_margin_pct: 10,
	overhead_pct: 10,
	template: 'general_civil',
	labour_rate_base: 'own_rates',
}

export function cloneSetup(form: MasterSetupForm): MasterSetupForm {
	return {
		...form,
		pipeline_stages: [...form.pipeline_stages],
		bid_weights: { ...form.bid_weights },
		lead_sources: [...form.lead_sources],
	}
}

/** Whether a form holds exactly the values of a preset. Lead source order does not count. */
export function matchesPreset(
	form: MasterSetupForm,
	preset: MasterSetupForm,
): boolean {
	const sorted = (values: string[]) => [...values].sort().join('|')
	return (
		form.pipeline_stages.join('|') === preset.pipeline_stages.join('|') &&
		form.deal_currency === preset.deal_currency &&
		WEIGHT_LABELS.every(
			({ key }) => form.bid_weights[key] === preset.bid_weights[key],
		) &&
		form.threshold === preset.threshold &&
		sorted(form.lead_sources) === sorted(preset.lead_sources) &&
		form.uom_system === preset.uom_system &&
		form.net_margin_pct === preset.net_margin_pct &&
		form.overhead_pct === preset.overhead_pct &&
		form.template === preset.template &&
		form.labour_rate_base === preset.labour_rate_base
	)
}

function clampPercent(value: number): number {
	if (!Number.isFinite(value)) return 0
	return Math.min(100, Math.max(0, Math.round(value)))
}

/**
 * Set one weight and share the rest of 100 between the others, in proportion to
 * their current values (equally when they are all zero). The result is whole
 * numbers that always add up to 100.
 */
export function rebalanceWeights(
	weights: Weights,
	key: WeightKey,
	value: number,
): Weights {
	const fixed = clampPercent(value)
	const others = WEIGHT_LABELS.map((entry) => entry.key).filter(
		(other) => other !== key,
	)
	const remainder = 100 - fixed
	const current = others.reduce((sum, other) => sum + weights[other], 0)
	const exact = others.map((other) =>
		current > 0
			? (weights[other] / current) * remainder
			: remainder / others.length,
	)
	const rounded = exact.map(Math.floor)
	let missing = remainder - rounded.reduce((sum, part) => sum + part, 0)
	// Largest remainder first, so the rounding error lands where it matters least.
	const order = exact
		.map((part, index) => ({ index, fraction: part - Math.floor(part) }))
		.sort((left, right) => right.fraction - left.fraction)
	for (const { index } of order) {
		if (missing <= 0) break
		rounded[index]++
		missing--
	}

	const result = { ...weights, [key]: fixed }
	others.forEach((other, index) => {
		result[other] = rounded[index]
	})
	return result
}

export function weightTotal(weights: Weights): number {
	return WEIGHT_LABELS.reduce((sum, { key }) => sum + weights[key], 0)
}

/** Why the form cannot be sent yet, or an empty list. */
export function setupErrors(form: MasterSetupForm): string[] {
	const errors: string[] = []
	if (weightTotal(form.bid_weights) !== 100)
		errors.push('The bid/no-bid weights must add up to 100%.')
	if (!form.pipeline_stages.length) errors.push('Keep at least one milestone.')
	for (const [label, value] of [
		['Target net margin', form.net_margin_pct],
		['Overhead rate', form.overhead_pct],
	] as const) {
		if (!Number.isFinite(value) || value < 0 || value > 100)
			errors.push(`${label} must be between 0 and 100%.`)
	}
	return errors
}

export function toMasterConfig(form: MasterSetupForm): MasterSetupConfig {
	return {
		crm: {
			lead_sources: [...form.lead_sources],
			bid_weights: { ...form.bid_weights },
			deal_currency: form.deal_currency,
			pipeline_stages: [...form.pipeline_stages],
			threshold: form.threshold,
		},
		estimation: {
			uom_system: form.uom_system,
			templates: [form.template],
			net_margin_pct: form.net_margin_pct,
			overhead_pct: form.overhead_pct,
			labour_rate_base: form.labour_rate_base,
		},
	}
}

/** Move one item of a list to another position. */
export function moveItem<T>(items: T[], from: number, to: number): T[] {
	if (from === to || from < 0 || from >= items.length) return [...items]
	const target = Math.min(Math.max(to, 0), items.length - 1)
	const next = [...items]
	const [item] = next.splice(from, 1)
	next.splice(target, 0, item)
	return next
}
