// Console feature flags, injected at page boot by central/www/dashboard.py from
// the Central Settings single (see window.features in env.d.ts). Static for the
// life of the page — a flag change takes a reload, like the rest of the boot data.
// Default on when the boot data is absent (e.g. the vite dev server, which doesn't
// run get_context), matching the DocType's default.

export interface Features {
	/** The Add-ons area as a whole (nav entry + routes). */
	addons: boolean
	/** Object storage rollout switch. */
	storage: boolean
	/** AI rollout switch. */
	llm: boolean
	/** The public IPv4 switch on the New server page. */
	publicIpv4: boolean
	/** The public IPv6 switch on the New server page. */
	publicIpv6: boolean
	/** The firewall switch on the New server page. */
	firewall: boolean
	/** Managed SaaS mode for this user: the console shows sites and products, and
	 *  Central keeps the server tools for operators. */
	managed: boolean
	/** Intrakore Cloud is invite-only: no public signup, and a new email needs an invitation. */
	inviteOnly: boolean
}

// Defaults match the DocType: the area is on, individual services off until rolled out.
export const features: Features = {
	addons: window.features?.addons ?? true,
	storage: window.features?.storage ?? import.meta.env.DEV,
	llm: window.features?.llm ?? import.meta.env.DEV,
	publicIpv4: window.features?.public_ipv4 ?? false,
	publicIpv6: window.features?.public_ipv6 ?? false,
	firewall: window.features?.firewall ?? false,
	managed: window.features?.managed ?? false,
	inviteOnly: window.features?.invite_only ?? true,
}
