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

/** The Checkout.com handles of a card setup or payment (`CheckoutAdapter._flow_handles`). */
export interface CheckoutSetup {
	public_key: string
	/** 'sandbox' or 'production'. */
	environment: string
	/** The payment session Checkout created, unchanged: id, token, secret and links. */
	payment_session: {
		id: string
		payment_session_token?: string
		payment_session_secret?: string
	}
	/** Where Flow loads from: Checkout.com's own host. */
	flow_script_url?: string
}
