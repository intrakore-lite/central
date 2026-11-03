<script setup lang="ts">
import { Alert } from 'frappe-ui'
import { computed, ref } from 'vue'
import PaymentMethodFlow from '@/components/billing/PaymentMethodFlow.vue'
import { useBillingSetup } from '@/composables/useBillingSetup'
import { useCapabilities } from '@/composables/useCapabilities'
import { useSession } from '@/composables/useSession'
import { formatDate } from '@/lib/format'

// The trial's reminder to add a payment method, in place of an onboarding dialog. It is
// shown until the trial is converted or the user closes it. A closed banner stays closed
// for that team on this browser.
const STORAGE_PREFIX = 'central.trial_payment_banner.dismissed.'

const { profile } = useBillingSetup()
const { canManageBilling } = useCapabilities()
const { activeTeam } = useSession()
const flow = ref<InstanceType<typeof PaymentMethodFlow> | null>(null)
const dismissedTeams = ref(new Set<string>())

const trial = computed(() =>
	profile.value?.open_trial?.state === 'Active'
		? profile.value.open_trial
		: null,
)

const isDismissed = computed(() => {
	const team = activeTeam.value
	if (!team) return true
	return (
		dismissedTeams.value.has(team) ||
		localStorage.getItem(STORAGE_PREFIX + team) === '1'
	)
})

const title = computed(() => {
	const endsOn = formatDate(trial.value?.ends_on)
	return endsOn
		? `Your free trial ends on ${endsOn}`
		: 'Your site is on a free trial'
})

const action = computed(() => ({
	label: 'Add payment method',
	onClick: () => flow.value?.start(),
}))

function dismiss(): void {
	const team = activeTeam.value
	if (!team) return
	localStorage.setItem(STORAGE_PREFIX + team, '1')
	dismissedTeams.value = new Set([...dismissedTeams.value, team])
}
</script>

<template>
	<template v-if="trial && canManageBilling">
		<Alert
			v-if="!isDismissed"
			class="m-2 mb-0"
			theme="blue"
			icon="lucide-calendar-clock"
			:title="title"
			description="Add a payment method to keep your site after the trial. Adding one ends the free trial today and starts billing for your plan."
			:primary-action="action"
			dismissible
			@dismiss="dismiss"
		/>
		<PaymentMethodFlow ref="flow" />
	</template>
</template>
