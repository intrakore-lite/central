/** The answers of onboarding step 1, and the billing details of step 2. */
export interface OnboardingProfile {
	full_name: string
	/** The session user. The activation link proved it. */
	email: string
	/** Stored with its country code, such as +971508329410. */
	mobile: string
	organisation: string
	business_type: string
	headcount_bracket: string
	turnover_band: string
	/** Zero until the owner chooses. */
	seats: number
	address_line1: string
	city: string
	country: string
	tax_id: string
}

/** The seat prices of Central Settings > Seat Billing. */
export interface SeatPricing {
	currency: string
	seat_price: number
	/** The base plan bills at least this many seats. */
	included_seats: number
	storage_price_per_gb: number
	trial_ai_cap: number
	vat_percent: number
	max_seats: number
	trial_days: number
	/** The price of every seat count from 1 to max_seats, computed by Central. */
	quotes: SeatQuote[]
}

export interface SeatQuote {
	seats: number
	billed_seats: number
	monthly: number
	vat: number
	total: number
}

export interface TrustLine {
	title: string
	text: string
}

export interface TrustQuote {
	text: string
	author: string
	role?: string
}

/** Central Settings > Onboarding Trust Content over its true defaults.
 *  See DEFAULT_TRUST_CONTENT in central/signups/onboarding.py. */
export interface TrustContent {
	profile_badge: string
	profile_footer: string[]
	profile_trust_line: string
	guarantee: TrustLine
	payment_badges: string[]
	proof: TrustLine
	benefits: string[]
	quote: TrustQuote | null
	help: TrustLine
	/** Steps 3 and 4. A null key shows nothing. */
	team_badge: string | null
	team_features: TrustLine[]
	team_stat: TrustStat | null
	team_caption: string | null
	setup_footer_line: string | null
}

/** A figure shown on step 3, only once Central Settings gives a real one. */
export interface TrustStat {
	label: string
	value: string
	note?: string
}

export interface OnboardingProduct {
	name: string
	title: string
	subtitle: string | null
	logo: string | null
	/** The product's own apps by title, such as CRM and Estimation. */
	modules: string[]
}

/** central.api.onboarding.get_onboarding */
export interface Onboarding {
	team: string
	product: OnboardingProduct | null
	profile: OnboardingProfile
	options: {
		business_type: string[]
		headcount_bracket: string[]
		turnover_band: string[]
	}
	pricing: SeatPricing
	trust: TrustContent
	has_payment_method: boolean
	progress: SetupProgress
}

/** The step the owner resumes at: 1 to 4, and 5 once onboarding is done. */
export interface SetupProgress {
	step: number
	done: boolean
}

export type SiteStage =
	| 'waiting'
	| 'building'
	| 'starting'
	| 'setting_up'
	| 'ready'
	| 'failed'

export interface SeatUsage {
	/** Null when the site has no seat cap. */
	cap: number | null
	used: number
	free: number | null
}

export interface ModuleSetupState {
	done: boolean
	at: string | null
}

/** central.api.onboarding.site_state */
export interface SiteSetupState {
	stage: SiteStage
	/** A rough share of the wait, from 0 to 100. */
	progress: number
	message: string | null
	site: { name: string; url: string } | null
	seats: SeatUsage | null
	company: string | null
	master_setup: Record<'crm' | 'estimation', ModuleSetupState> | null
}

export interface InviteResult {
	email: string
	status: 'created' | 'enabled' | 'updated' | 'unchanged' | 'error'
	roles: string[]
	missing_roles?: string[]
	email_sent: boolean
	error?: string
}

/** central.api.onboarding.invite_members */
export interface InviteResponse {
	results: InviteResult[]
	seats: SeatUsage
}

/** central.api.onboarding.apply_master_setup */
export interface MasterSetupReport {
	applied: Record<string, unknown>
	/** Keys the site has no place for yet, with the reason. */
	skipped: Record<string, string>
	failed: Record<string, string>
	site: string | null
}

/** What the card setup of the payment gateway hands the page. */
export interface CardSetupHandles {
	payment_method?: string
	/** Stripe: confirmed in Stripe Elements. */
	client_secret?: string
	/** A framed hosted payment page. */
	iframe_url?: string
	/** A hosted payment page the browser leaves to, and returns from. */
	redirect_url?: string
	/** Checkout.com: the card is taken in the page by Checkout Flow. */
	checkout?: CheckoutSetup
}

/** The Checkout.com handles of a card setup. Align with the Checkout adapter once it lands. */
export interface CheckoutSetup {
	public_key: string
	/** 'sandbox' or 'production'. */
	environment: string
	/** The payment session Checkout created for this setup: id, token and secret. */
	payment_session: {
		id: string
		payment_session_token?: string
		payment_session_secret?: string
	}
}
