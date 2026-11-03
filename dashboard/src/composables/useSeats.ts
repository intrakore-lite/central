import { useCall } from 'frappe-ui'
import { computed, ref } from 'vue'
import { API, method } from '@/api/methods'
import { useSession } from '@/composables/useSession'
import { teamParams, whenTeamReady } from '@/composables/useTeamScope'
import { getErrorMessage, successToast } from '@/lib/feedback'
import { submitOrThrow } from '@/lib/frappeCall'
import type { SeatSummary } from '@/types/billing'

// The team's seats in Settings > Billing: the current price, a preview of a new count, the
// change itself and the cancellation. A module singleton, so a change reloads every reader.
const { activeTeam } = useSession()

const summaryCall = useCall<SeatSummary, { team: string }>({
	url: method(API.seats),
	params: teamParams,
	immediate: false,
	refetch: true,
})
whenTeamReady(() => summaryCall.reload())

const previewParams = ref<{ team: string; seat_count: number }>({
	team: '',
	seat_count: 0,
})
const previewCall = useCall<SeatSummary, typeof previewParams.value>({
	url: method(API.seats),
	params: () => previewParams.value,
	immediate: false,
})
const changeCall = useCall<SeatSummary, { team: string; seat_count: number }>({
	url: method(API.changeSeats),
	method: 'POST',
	immediate: false,
})
const cancelCall = useCall<SeatSummary, { team: string; cancelled: boolean }>({
	url: method(API.setSubscriptionCancelled),
	method: 'POST',
	immediate: false,
})

const saving = ref(false)
const error = ref('')

async function run(
	action: () => Promise<void>,
	done: string,
): Promise<boolean> {
	saving.value = true
	error.value = ''
	try {
		await action()
		await summaryCall.reload()
		successToast(done)
		return true
	} catch (failure) {
		error.value = getErrorMessage(failure)
		return false
	} finally {
		saving.value = false
	}
}

export function useSeats() {
	return {
		summary: computed(() => summaryCall.data ?? null),
		loading: computed(() => summaryCall.loading && !summaryCall.data),
		loadError: computed(() =>
			summaryCall.error ? getErrorMessage(summaryCall.error) : '',
		),
		preview: computed(() => previewCall.data ?? null),
		previewLoading: computed(() => previewCall.loading),
		saving,
		error,

		reload: (): Promise<unknown> => summaryCall.reload(),

		previewSeats(seatCount: number): Promise<unknown> {
			previewParams.value = { team: activeTeam.value!, seat_count: seatCount }
			return previewCall.reload()
		},

		changeSeats: (seatCount: number): Promise<boolean> =>
			run(
				() =>
					submitOrThrow(changeCall, {
						team: activeTeam.value!,
						seat_count: seatCount,
					}),
				`Seats changed to ${seatCount}`,
			),

		setCancelled: (cancelled: boolean): Promise<boolean> =>
			run(
				() => submitOrThrow(cancelCall, { team: activeTeam.value!, cancelled }),
				cancelled ? 'Subscription cancelled' : 'Subscription kept',
			),

		clearError(): void {
			error.value = ''
		},
	}
}
