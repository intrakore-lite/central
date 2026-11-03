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
				// The Intrakore Construction Cloud tokens of the onboarding pages (Stitch DESIGN.md).
				// Only the onboarding layout uses the `ik` names, so the console keeps Espresso.
				ik: {
					primary: '#0022e6',
					'primary-hover': '#001dc4',
					'primary-deep': '#0016a7',
					'primary-soft': '#dfe0ff',
					ink: '#0b122f',
					text: '#171c24',
					muted: '#444556',
					slate: '#4b556d',
					outline: '#757688',
					placeholder: '#8c97b7',
					canvas: '#eef2fe',
					'canvas-soft': '#f5f8ff',
					panel: '#f0f3ff',
					chip: '#eaeefa',
					'chip-hover': '#e4e8f4',
					line: '#dee2ee',
					border: '#dde3f5',
					control: '#cbd5e1',
					jade: '#10b981',
					'jade-soft': '#e6f9f2',
					'jade-bright': '#4edea3',
					amber: '#fbbf24',
					'jade-ink': '#005539',
					error: '#ba1a1a',
					'error-soft': '#ffdad6',
				},
			},
			fontFamily: {
				ik: ['"Plus Jakarta Sans Variable"', 'system-ui', 'sans-serif'],
			},
			fontSize: {
				'ik-display': [
					'44px',
					{ lineHeight: '52px', letterSpacing: '-0.03em', fontWeight: '800' },
				],
				'ik-display-mobile': [
					'32px',
					{ lineHeight: '40px', letterSpacing: '-0.02em', fontWeight: '800' },
				],
				'ik-headline': [
					'30px',
					{ lineHeight: '38px', letterSpacing: '-0.02em', fontWeight: '700' },
				],
				'ik-headline-mobile': [
					'24px',
					{ lineHeight: '32px', letterSpacing: '-0.015em', fontWeight: '700' },
				],
				'ik-title': [
					'22px',
					{ lineHeight: '28px', letterSpacing: '-0.01em', fontWeight: '700' },
				],
				'ik-kicker': [
					'12px',
					{ lineHeight: '16px', letterSpacing: '0.08em', fontWeight: '800' },
				],
				'ik-body-lg': [
					'17px',
					{ lineHeight: '26px', letterSpacing: '-0.01em', fontWeight: '400' },
				],
				'ik-body': [
					'15px',
					{ lineHeight: '22px', letterSpacing: '0em', fontWeight: '400' },
				],
				'ik-body-sm': [
					'13px',
					{ lineHeight: '18px', letterSpacing: '0em', fontWeight: '500' },
				],
				'ik-label-lg': [
					'15px',
					{ lineHeight: '20px', letterSpacing: '-0.005em', fontWeight: '600' },
				],
				'ik-label': [
					'14px',
					{ lineHeight: '18px', letterSpacing: '0em', fontWeight: '600' },
				],
				'ik-label-sm': [
					'12px',
					{ lineHeight: '16px', letterSpacing: '0.02em', fontWeight: '600' },
				],
			},
			borderRadius: {
				'ik-sm': '8px',
				'ik-md': '12px',
				'ik-lg': '16px',
				'ik-xl': '24px',
			},
			boxShadow: {
				'ik-1':
					'0 1px 3px rgba(11, 18, 47, 0.04), 0 1px 2px rgba(11, 18, 47, 0.02)',
				'ik-2':
					'0 16px 40px -12px rgba(11, 18, 47, 0.08), 0 4px 16px -4px rgba(0, 34, 230, 0.05)',
				'ik-3':
					'0 0 0 4px rgba(0, 34, 230, 0.12), 0 8px 20px -4px rgba(0, 34, 230, 0.2)',
				'ik-header': '0 1px 8px rgba(0, 0, 0, 0.04)',
				'ik-control': '0 0 0 1px #cbd5e1',
				'ik-line': '0 0 0 1px #d1d8ed',
				'ik-invalid': '0 0 0 1px #ba1a1a',
				'ik-focus': '0 0 0 1px #0022e6, 0 0 0 4px rgba(0, 34, 230, 0.12)',
				'ik-button': '0 4px 12px -2px rgba(0, 34, 230, 0.3)',
				'ik-hero': '0 25px 50px -12px rgba(11, 18, 47, 0.18)',
			},
		},
	},
}
