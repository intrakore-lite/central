<script setup lang="ts">
import { Alert, frappeRequest } from 'frappe-ui'
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { API, methodV1 } from '@/api/methods'

interface TrialOffer {
	product: string
	title: string
	logo: string | null
}

const props = defineProps<{ team: string }>()

const router = useRouter()
const offer = ref<TrialOffer | null>(null)

// Central offers the default trial product only to a team whose next site is free and
// whose owner has no open trial. The banner shows nothing when there is no offer.
watch(
	() => props.team,
	async (team) => {
		offer.value = null
		try {
			const result = await frappeRequest<TrialOffer | null>({
				url: methodV1(API.trialOffer),
				method: 'GET',
				params: { team },
			})
			if (team === props.team) offer.value = result
		} catch {
			// The offer is a shortcut. The New site button still creates a site.
		}
	},
	{ immediate: true },
)

const action = computed(() =>
	offer.value
		? {
				label: 'Start free trial',
				onClick: () =>
					router.push({
						path: '/onboarding/site',
						query: { product: offer.value?.product },
					}),
			}
		: undefined,
)
</script>

<template>
	<Alert
		v-if="offer"
		class="m-2 mb-0"
		theme="blue"
		icon="lucide-sparkles"
		:title="`Start your free ${offer.title} trial`"
		description="Name your site and it is ready in a few minutes, with its apps installed. No payment method needed to start."
		:primary-action="action"
	/>
</template>
