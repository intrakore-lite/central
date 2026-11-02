/// <reference types="vite/client" />
/// <reference types="unplugin-icons/types/vue" />

/** The bench's Socket.IO port, compiled in by vite.config.ts. Null when no bench config
 *  was found at build time. */
declare const __SOCKETIO_PORT__: number | null

declare module '*.vue' {
	import type { DefineComponent } from 'vue'

	const component: DefineComponent<Record<string, unknown>>
	export default component
}

// Boot data injected by central/www/dashboard.py (see jinjaBootData in vite.config).
// frappe-ui's request layer reads window.csrf_token for write (POST) calls.
interface Window {
	csrf_token?: string
	user?: string
	user_type?: string
	site_name?: string
	socketio_port?: number
	/** Site timezone Frappe stores naive datetimes in. See dashboard.py. */
	system_timezone?: string
	/** Days a new team invitation stays open, from Central Settings. */
	invitation_expiry_days?: number
	/** Upload limit in bytes, from System Settings. */
	max_file_size?: number
	/** Help menu links from Central Settings. Null when an operator left one empty. */
	help_links?: {
		support_ticket_url?: string | null
		feedback_url?: string | null
	}
	/** Brand from Central Settings. See central/branding.py and lib/brand.ts. */
	brand?: {
		title?: string
		logo_url?: string | null
		policies_url?: string | null
	}
	/** The free trial the sign-in page offers. See central/signups/trial_offer.py. */
	trial_offer?: {
		product: string
		title: string
		days: number
	} | null
	features?: {
		addons?: boolean
		storage?: boolean
		llm?: boolean
		public_ipv4?: boolean
		public_ipv6?: boolean
		firewall?: boolean
	}
}
