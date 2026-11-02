import intrakoreLogo from '@/assets/brand/intrakore-logo.svg'

// The platform's name, logo and policies page, injected at page boot by
// central/www/dashboard.py from Central Settings (see central/branding.py).
// The bundled INTRAKORE defaults apply when the boot data is absent, as on the
// vite dev server.

export interface Brand {
	/** The product name, such as "Intrakore Cloud". */
	name: string
	/** A square logo URL. */
	logo: string
	/** The terms and policies page. Null hides the terms notice. */
	policiesUrl: string | null
	/** The customer guide built from docs/ in this repository. */
	docsUrl: string
}

export const brand: Brand = {
	name: window.brand?.title || 'Intrakore Cloud',
	logo: window.brand?.logo_url || intrakoreLogo,
	policiesUrl: window.brand?.policies_url ?? null,
	docsUrl: 'https://intrakore-lite.github.io/central',
}
