import { useCall } from 'frappe-ui'
import { computed, ref } from 'vue'
import { API, method } from '@/api/methods'
import { useAuth } from '@/composables/useAuth'
import { getErrorMessage } from '@/lib/feedback'
import type { TrialActivation, TrialActivationResult } from '@/types/api'

/** What the activation page asks the visitor to do next. */
export type ActivationStep =
	| 'loading'
	| 'invalid'
	| 'expired'
	| 'activate'
	| 'sign-in'
	| 'wrong-account'

/** The Intrakore Cloud invitation behind an emailed activation link, and the action that spends it. */
export function useTrialActivation(token: string) {
	const { currentUser, logout } = useAuth()
	const busy = ref(false)
	const error = ref('')

	const activationCall = useCall<TrialActivation, { token: string }>({
		url: method(API.getTrialActivation),
		params: { token },
	})
	const activateCall = useCall<TrialActivationResult, { token: string }>({
		url: method(API.activateTrialInvitation),
		method: 'POST',
		immediate: false,
	})

	const activation = computed(() => activationCall.data ?? null)

	const step = computed<ActivationStep>(() => {
		if (activationCall.loading && !activation.value) return 'loading'
		if (!activation.value) return 'invalid'
		if (activation.value.status !== 'Sent') return 'expired'
		if (currentUser.value && currentUser.value !== activation.value.email)
			return 'wrong-account'
		if (!currentUser.value && activation.value.has_account) return 'sign-in'
		return 'activate'
	})

	const signInPath = computed(() => ({
		path: '/login',
		query: {
			email: activation.value?.email ?? '',
			'redirect-to': `/dashboard/activate?${new URLSearchParams({ token })}`,
		},
	}))

	async function run(action: () => Promise<void>, fallback: string) {
		busy.value = true
		error.value = ''
		try {
			await action()
		} catch (exception) {
			error.value = getErrorMessage(exception, fallback)
			busy.value = false
		}
	}

	// A full load boots the console with the new session. `busy` stays on until it leaves.
	const activate = () =>
		run(async () => {
			const result = await activateCall.submit({ token })
			if (activateCall.error || !result) throw activateCall.error
			if ('needs_sign_in' in result) {
				await activationCall.reload()
				busy.value = false
				return
			}
			window.location.replace(result.next)
		}, "We couldn't activate your account.")

	const switchAccount = () =>
		run(async () => {
			await logout()
			window.location.reload()
		}, "We couldn't sign you out.")

	return {
		activation,
		step,
		loadError: computed(() =>
			getErrorMessage(
				activationCall.error,
				'This activation link is not valid.',
			),
		),
		signInPath,
		busy,
		error,
		activate,
		switchAccount,
	}
}
