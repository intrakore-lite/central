// What a customer of a managed console reads in place of server details. With
// `features.managed` on, the console names a site by its address and its product, and
// keeps the machine (vCPU, memory, disk, addresses, region, provider) for operators.
// Pure, so the node tests can load it without Vue.

/** One fact on a site's overview: a label, a value and an icon. */
export interface SiteFact {
	key: 'address' | 'product' | 'plan' | 'seats' | 'storage' | 'status'
	label: string
	value: string
	icon: string
	/** Set for the site address, which opens in a new tab. */
	href?: string
}

/** "https://acme.intrakore.cloud" from a site URL or a bare hostname; '' when unknown. */
export function siteAddress(url?: string | null): string {
	const text = (url ?? '').trim()
	if (!text) return ''
	const withScheme = /^[a-z][a-z0-9+.-]*:\/\//i.test(text)
		? text
		: `https://${text}`
	try {
		const parsed = new URL(withScheme)
		return parsed.host ? `https://${parsed.host}` : ''
	} catch {
		return ''
	}
}

/** The line under a row's name: the site address, else the product, else the status. */
export function customerLine(row: {
	site?: { url: string | null; name?: string } | null
	productTitle?: string | null
	visual: { label: string }
}): string {
	return (
		siteAddress(row.site?.url ?? row.site?.name) ||
		(row.productTitle ?? '').trim() ||
		row.visual.label
	)
}

/** A team's seats, read defensively: the `seats` field is new and may be absent. */
export function teamSeats(team?: object | null): number | null {
	const seats = (team as { seats?: unknown } | null | undefined)?.seats
	const count = typeof seats === 'string' ? Number(seats) : seats
	return typeof count === 'number' && Number.isFinite(count) && count > 0
		? Math.floor(count)
		: null
}

/** "3 of 10 seats" when the team has seats, "3 members" when it does not yet. */
export function seatsLabel(
	team?: { members?: number | null } | null,
): string | null {
	if (!team) return null
	const members = team.members ?? 0
	const seats = teamSeats(team)
	if (seats) return `${members} of ${seats} seat${seats === 1 ? '' : 's'}`
	if (!members) return null
	return `${members} member${members === 1 ? '' : 's'}`
}

/** A plan's name without the size suffix Central appends ("Starter · 2 vCPU" → "Starter"). */
export function planName(title?: string | null): string {
	return (title ?? '').split(' · ')[0].trim()
}

/** The facts a customer reads about a site, in order; a fact with no value is left out. */
export function siteFacts(input: {
	siteUrl?: string | null
	productTitle?: string | null
	planTitle?: string | null
	team?: { members?: number | null } | null
	storageUsed?: string | null
	status: string
}): SiteFact[] {
	const address = siteAddress(input.siteUrl)
	const facts: (SiteFact | null)[] = [
		address
			? {
					key: 'address',
					label: 'Site address',
					value: address,
					icon: 'lucide-globe',
					href: address,
				}
			: null,
		fact('product', 'Product', input.productTitle, 'lucide-package'),
		fact('plan', 'Plan', planName(input.planTitle), 'lucide-receipt'),
		fact('seats', 'Seats', seatsLabel(input.team), 'lucide-users'),
		fact('storage', 'Storage used', input.storageUsed, 'lucide-database'),
		fact('status', 'Status', input.status, 'lucide-activity'),
	]
	return facts.filter((item): item is SiteFact => !!item)
}

function fact(
	key: SiteFact['key'],
	label: string,
	value: string | null | undefined,
	icon: string,
): SiteFact | null {
	const text = (value ?? '').trim()
	return text ? { key, label, value: text, icon } : null
}
