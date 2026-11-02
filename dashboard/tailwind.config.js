import frappeUIPreset from 'frappe-ui/tailwind'

/** @type {import('tailwindcss').Config} */
export default {
	presets: [frappeUIPreset],
	content: [
		'./index.html',
		'./src/**/*.{vue,js,ts,jsx,tsx,svg}',
		'./node_modules/frappe-ui/src/**/*.{vue,js,ts,jsx,tsx}',
		'./node_modules/frappe-ui/frappe/**/*.{vue,js,ts,jsx,tsx}',
		// The experimental family (ListView, Accordion, CodeEditor …) ships its own
		// utilities. Left unscanned, classes used only there — min-w-full on ListView's
		// grid, for one — never compile, and the component silently mis-sizes.
		'./node_modules/frappe-ui/experimental/**/*.{vue,js,ts,jsx,tsx}',
	],
	theme: {
		extend: {
			colors: {
				// The INTRAKORE brand palette. 700 is the brand blue of the logo.
				blueprint: {
					50: '#ebecff',
					100: '#d6d9ff',
					200: '#b9befe',
					300: '#8d95f6',
					400: '#5763fa',
					500: '#2a37f4',
					600: '#0717e4',
					700: '#000fcc',
					800: '#0310aa',
					900: '#050d76',
				},
			},
		},
	},
}
