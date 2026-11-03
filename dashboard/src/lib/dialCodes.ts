/** A mobile country code the onboarding offers, with the Frappe Country it bills in. */
export interface DialCode {
	code: string
	country: string
	flag: string
}

// GCC first, then the markets Intrakore Cloud customers most often dial from.
export const DIAL_CODES: DialCode[] = [
	{ code: '+971', country: 'United Arab Emirates', flag: '🇦🇪' },
	{ code: '+966', country: 'Saudi Arabia', flag: '🇸🇦' },
	{ code: '+974', country: 'Qatar', flag: '🇶🇦' },
	{ code: '+965', country: 'Kuwait', flag: '🇰🇼' },
	{ code: '+973', country: 'Bahrain', flag: '🇧🇭' },
	{ code: '+968', country: 'Oman', flag: '🇴🇲' },
	{ code: '+20', country: 'Egypt', flag: '🇪🇬' },
	{ code: '+962', country: 'Jordan', flag: '🇯🇴' },
	{ code: '+91', country: 'India', flag: '🇮🇳' },
	{ code: '+92', country: 'Pakistan', flag: '🇵🇰' },
	{ code: '+44', country: 'United Kingdom', flag: '🇬🇧' },
	{ code: '+1', country: 'United States', flag: '🇺🇸' },
]

export const DEFAULT_DIAL_CODE = DIAL_CODES[0]

/** A stored mobile such as "+971508329410" split into its dial code and local number.
 *  The longest matching code wins, so "+1" never takes a "+1..." number from a longer code. */
export function splitMobile(mobile: string): {
	dial: DialCode
	number: string
} {
	const compact = mobile.replace(/[\s()-]/g, '')
	const dial = [...DIAL_CODES]
		.sort((a, b) => b.code.length - a.code.length)
		.find((entry) => compact.startsWith(entry.code))
	if (!dial) return { dial: DEFAULT_DIAL_CODE, number: compact }
	return { dial, number: compact.slice(dial.code.length) }
}

/** The local number with its dial code, as the billing profile stores it. */
export function joinMobile(dial: DialCode, number: string): string {
	const local = number.replace(/[\s()-]/g, '').replace(/^0+/, '')
	return local ? `${dial.code}${local}` : ''
}
