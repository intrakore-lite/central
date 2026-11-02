import intrakoreLogo from '@/assets/brand/intrakore-logo.svg'
import intrakoreWordmark from '@/assets/brand/intrakore-wordmark.png'
import signInImage from '@/assets/brand/login-showcase.webp'
import trialImage from '@/assets/brand/signup-showcase.webp'

// The platform's name, logo and policies page, injected at page boot by
// central/www/dashboard.py from Central Settings (see central/branding.py).
// The bundled INTRAKORE defaults apply when the boot data is absent, as on the
// vite dev server.

const DEFAULT_NAME = 'Intrakore Cloud'

export interface Brand {
	/** The product name, such as "Intrakore Cloud". */
	name: string
	/** A square logo URL. */
	logo: string
	/** The INTRAKORE wordmark. Null when an operator renames the brand or uploads a logo. */
	wordmark: string | null
	/** The terms and policies page. Null hides the terms notice. */
	policiesUrl: string | null
	/** The customer guide built from docs/ in this repository. */
	docsUrl: string
}

const name = window.brand?.title || DEFAULT_NAME
const uploadedLogo = window.brand?.logo_url

export const brand: Brand = {
	name,
	logo: uploadedLogo || intrakoreLogo,
	wordmark: !uploadedLogo && name === DEFAULT_NAME ? intrakoreWordmark : null,
	policiesUrl: window.brand?.policies_url ?? null,
	docsUrl: 'https://intrakore-lite.github.io/central',
}

export interface TrialOffer {
	/** The Product key, such as "crm-estimation". */
	product: string
	title: string
	days: number
}

/** The free trial the sign-in page offers, from Central Settings > Default Trial Product. */
export const trialOffer: TrialOffer | null = window.trial_offer ?? null

export interface AuthShowcase {
	eyebrow: string
	headline: string
	summary: string
	image: string
}

// The marketing copy beside the auth forms, in the words of intrakore.com. Keep every claim
// true for this platform: it does not run in the UAE, so never say "Hosted in the UAE".
export const trustLine = 'Trusted by 500+ construction customers across the UAE'

export const signInShowcase: AuthShowcase = {
	eyebrow: 'Construction Management Software',
	headline: 'From first tender to final accounts. One platform.',
	summary:
		'Qualify tenders with a bid/no-bid matrix, hand every won bid straight to estimation, and price from shared BOQs and rate books.',
	image: signInImage,
}

/** The copy beside the trial signup of one product. */
export function trialShowcase(
	productTitle: string,
	days?: number,
): AuthShowcase {
	return {
		eyebrow: days ? `Free ${days}-day trial` : 'Free trial',
		headline: `Try ${productTitle} on your own tenders.`,
		summary:
			'No card needed to start. We ask for one only if you keep your site after the trial.',
		image: trialImage,
	}
}

/** The trial days of a product, known only for the offered trial. */
export function trialDays(productKey: string): number | undefined {
	return trialOffer?.product === productKey ? trialOffer.days : undefined
}
