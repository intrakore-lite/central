<script setup lang="ts">
import { computed, onMounted, reactive, ref, useTemplateRef } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { API } from '@/api/methods'
import PaymentCardFrame from '@/components/onboarding/setup/PaymentCardFrame.vue'
import PlanSummaryCard from '@/components/onboarding/setup/PlanSummaryCard.vue'
import SetupField from '@/components/onboarding/setup/SetupField.vue'
import SetupHelpRibbon from '@/components/onboarding/setup/SetupHelpRibbon.vue'
import SetupLoadError from '@/components/onboarding/setup/SetupLoadError.vue'
import SetupSelect from '@/components/onboarding/setup/SetupSelect.vue'
import SetupShell from '@/components/onboarding/setup/SetupShell.vue'
import SetupSubmitButton from '@/components/onboarding/setup/SetupSubmitButton.vue'
import SetupTextInput from '@/components/onboarding/setup/SetupTextInput.vue'
import TrialTimeline from '@/components/onboarding/setup/TrialTimeline.vue'
import TrustProofCard from '@/components/onboarding/setup/TrustProofCard.vue'
import { useSetupOnboarding } from '@/composables/useSetupOnboarding'
import { frappeErrorMessage, getFrappe, methodUrl } from '@/lib/auth'
import { carriedQuery } from '@/lib/authRedirect'
import { brand } from '@/lib/brand'

const BADGE_ICONS = ['lucide-shield-check', 'lucide-lock', 'lucide-server']

const route = useRoute()
const router = useRouter()
const {
	team,
	onboarding,
	pricing,
	loading,
	loadError,
	load,
	quoteFor,
	saveBillingDetails,
	startSite,
	resume,
} = useSetupOnboarding()
const cardFrame = useTemplateRef<InstanceType<typeof PaymentCardFrame>>('card')

const details = reactive({
	address_line1: '',
	city: '',
	country: '',
	tax_id: '',
})
const countries = ref<string[]>([])
const savedDetails = ref('')
const isCardActive = ref(false)
const isOpening = ref(false)
const isSubmitting = ref(false)
const showDetailErrors = ref(false)
const error = ref('')

const product = computed(() => onboarding.value?.product ?? null)
const productTitle = computed(() => product.value?.title ?? brand.name)
const seats = computed(
	() => onboarding.value?.profile.seats || pricing.value?.included_seats || 1,
)
const detailErrors = computed(() => {
	if (!showDetailErrors.value) return {}
	return {
		address_line1: details.address_line1.trim()
			? ''
			: 'Enter the billing address.',
		city: details.city.trim() ? '' : 'Enter the city.',
		country: details.country ? '' : 'Choose the country.',
	}
})
const hasCard = computed(() => Boolean(onboarding.value?.has_payment_method))
const canSubmit = computed(
	() => hasCard.value || Boolean(cardFrame.value?.isReady),
)

onMounted(async () => {
	void loadCountries()
	await load()
	if (await resume(2)) return
	const profile = onboarding.value?.profile
	if (!profile) return
	if (!profile.organisation) {
		await router.replace({
			path: '/onboarding/profile',
			query: carriedQuery(route.query),
		})
		return
	}
	Object.assign(details, {
		address_line1: profile.address_line1,
		city: profile.city,
		country: profile.country,
		tax_id: profile.tax_id,
	})
	savedDetails.value = JSON.stringify(details)
	isCardActive.value = Boolean(
		profile.address_line1 && profile.city && profile.country,
	)
})

async function loadCountries() {
	try {
		const geo = await getFrappe<{ countries: string[] }>(
			methodUrl(API.billingGeo),
		)
		countries.value = geo.countries
	} catch {
		// The saved country stays a choice, so the step can still go on.
	}
}

const countryOptions = computed(() =>
	details.country && !countries.value.includes(details.country)
		? [details.country, ...countries.value]
		: countries.value,
)

// The card setup needs a complete billing profile, so the address is saved before the form opens.
async function saveDetails(): Promise<boolean> {
	showDetailErrors.value = true
	if (Object.values(detailErrors.value).some(Boolean)) return false
	if (JSON.stringify(details) === savedDetails.value) return true
	try {
		await saveBillingDetails({ ...details })
		savedDetails.value = JSON.stringify(details)
		return true
	} catch (exception) {
		error.value = frappeErrorMessage(
			exception,
			'Could not save the billing details. Try again.',
		)
		return false
	}
}

async function openCard() {
	error.value = ''
	isOpening.value = true
	isCardActive.value = await saveDetails()
	isOpening.value = false
}

async function submit() {
	if (isSubmitting.value) return
	error.value = ''
	isSubmitting.value = true
	try {
		if (!(await saveDetails())) return
		if (!hasCard.value) {
			const failure =
				(await cardFrame.value?.confirm()) ?? 'Open the card form first.'
			if (failure) {
				error.value = failure
				return
			}
		}
		await startSite()
		await router.push({
			path: '/onboarding/team',
			query: carriedQuery(route.query),
		})
	} catch (exception) {
		error.value = frappeErrorMessage(
			exception,
			'Your card is saved, but your site could not start. Try again.',
		)
	} finally {
		isSubmitting.value = false
	}
}
</script>

<template>
	<SetupShell :step="2">
		<div class="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 md:py-12 lg:px-8">
			<div
				class="mb-8 flex flex-col justify-between gap-4 sm:flex-row sm:items-center"
			>
				<div>
					<p
						class="mb-2 inline-flex items-center gap-2 rounded-full bg-ik-primary-soft/60 px-3 py-1 text-ik-kicker uppercase text-ik-primary"
					>
						<span
							class="size-2 animate-pulse rounded-full bg-ik-primary"
							aria-hidden="true"
						/>
						Step 2 of 4: Payment &amp; Trial Activation
					</p>
					<h1 class="text-ik-headline-mobile text-ik-text md:text-ik-headline">
						Activate your {{ pricing?.trial_days ?? 30 }}-day risk-free trial
					</h1>
					<p class="mt-1 text-ik-body text-ik-slate">
						Full access today with zero initial charge. Cancel any time before
						your first debit.
					</p>
				</div>
				<div
					v-if="onboarding"
					class="flex items-center gap-3 self-start rounded-ik-md bg-white px-4 py-2.5 shadow-ik-1 sm:self-auto"
				>
					<span
						class="flex size-9 items-center justify-center rounded-ik-sm bg-ik-jade-soft text-ik-jade-ink"
						aria-hidden="true"
					>
						<span class="lucide-shield-check size-5" />
					</span>
					<div>
						<p class="text-ik-label-sm font-bold text-ik-text">
							{{ onboarding.trust.guarantee.title }}
						</p>
						<p
							class="text-ik-kicker normal-case tracking-tight text-ik-jade-ink"
						>
							{{ onboarding.trust.guarantee.text }}
						</p>
					</div>
				</div>
			</div>

			<div
				v-if="loading"
				class="grid grid-cols-1 gap-8 lg:grid-cols-12"
				aria-busy="true"
				aria-label="Loading your plan"
			>
				<div class="h-96 animate-pulse rounded-ik-lg bg-white lg:col-span-7" />
				<div class="h-96 animate-pulse rounded-ik-lg bg-white lg:col-span-5" />
			</div>

			<SetupLoadError
				v-else-if="loadError"
				class="max-w-xl"
				:message="loadError"
				@retry="load"
			/>

			<div
				v-else-if="onboarding && pricing"
				class="grid grid-cols-1 items-start gap-8 lg:grid-cols-12"
			>
				<div class="flex flex-col gap-6 lg:col-span-7">
					<TrialTimeline
						:trial-days="pricing.trial_days"
						:currency="pricing.currency"
						:modules="product?.modules ?? []"
						:product-title="productTitle"
					/>

					<section
						class="rounded-ik-lg bg-white p-6 shadow-ik-1 md:p-8"
						aria-labelledby="payment-title"
					>
						<div class="flex flex-wrap items-center justify-between gap-3 pb-6">
							<div class="flex items-center gap-3">
								<span
									class="flex size-10 items-center justify-center rounded-ik-md bg-ik-primary-soft/40 text-ik-primary"
									aria-hidden="true"
								>
									<span class="lucide-credit-card size-5" />
								</span>
								<div>
									<h2 id="payment-title" class="text-ik-title text-ik-text">
										Payment Method
									</h2>
									<p class="text-ik-body-sm text-ik-slate">
										Credit card or corporate procurement card
									</p>
								</div>
							</div>
							<div
								class="flex items-center gap-1.5"
								aria-label="Accepted cards"
							>
								<span
									v-for="network in ['VISA', 'MC', 'AMEX']"
									:key="network"
									class="rounded bg-ik-chip px-2 py-1 text-ik-kicker text-ik-text"
								>
									{{ network }}
								</span>
							</div>
						</div>

						<form class="space-y-4" novalidate @submit.prevent="submit">
							<p
								v-if="hasCard"
								class="flex items-center gap-2 rounded-ik-md bg-ik-jade-soft px-4 py-3 text-ik-body-sm text-ik-jade-ink"
							>
								<span class="lucide-circle-check size-4" aria-hidden="true" />
								Your card is saved. Nothing is charged today.
							</p>

							<SetupField
								for="billing-address"
								label="Corporate Billing Address"
								:error="detailErrors.address_line1"
							>
								<SetupTextInput
									id="billing-address"
									v-model="details.address_line1"
									icon="lucide-map-pin"
									placeholder="Office / Suite, Street Address"
									autocomplete="street-address"
									:invalid="Boolean(detailErrors.address_line1)"
								/>
							</SetupField>
							<div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
								<SetupField
									for="billing-city"
									label="City"
									:error="detailErrors.city"
								>
									<SetupTextInput
										id="billing-city"
										v-model="details.city"
										icon="lucide-building"
										placeholder="Dubai"
										autocomplete="address-level2"
										:invalid="Boolean(detailErrors.city)"
									/>
								</SetupField>
								<SetupField
									for="billing-country"
									label="Country"
									:error="detailErrors.country"
								>
									<SetupSelect
										id="billing-country"
										v-model="details.country"
										icon="lucide-globe"
										placeholder="Choose a country"
										:options="countryOptions"
										:invalid="Boolean(detailErrors.country)"
									/>
								</SetupField>
							</div>
							<SetupField
								for="billing-trn"
								label="Tax Registration Number (VAT / TRN)"
							>
								<template #aside>
									<span class="text-ik-label-sm text-ik-outline">
										Optional for UAE / GCC
									</span>
								</template>
								<SetupTextInput
									id="billing-trn"
									v-model="details.tax_id"
									icon="lucide-receipt"
									placeholder="100-XXXX-XXXX-XXX3"
									:maxlength="20"
								/>
							</SetupField>

							<PaymentCardFrame
								v-if="!hasCard"
								ref="card"
								class="pt-2"
								:team="team ?? ''"
								:active="isCardActive && Boolean(team)"
								:opening="isOpening"
								@open="openCard"
								@saved="submit"
							/>

							<ul
								class="flex flex-wrap items-center gap-x-4 gap-y-2 pb-2 pt-3 text-ik-label-sm text-ik-slate"
							>
								<li
									v-for="(badge, index) in onboarding.trust.payment_badges"
									:key="badge"
									class="flex items-center gap-1.5"
								>
									<span
										v-if="index > 0"
										class="mr-2.5 size-1 rounded-full bg-ik-line"
										aria-hidden="true"
									/>
									<span
										class="size-4"
										:class="[
											BADGE_ICONS[index % BADGE_ICONS.length],
											index === 1 ? 'text-ik-primary' : 'text-ik-jade-ink',
										]"
										aria-hidden="true"
									/>
									{{ badge }}
								</li>
							</ul>

							<p
								v-if="error"
								class="rounded-ik-md bg-ik-error-soft px-4 py-3 text-ik-body-sm text-ik-error"
								role="alert"
							>
								{{ error }}
							</p>

							<div class="pt-4">
								<SetupSubmitButton
									:label="
										hasCard
											? 'Proceed to Team Setup'
											: 'Confirm Card & Proceed to Team Setup'
									"
									:loading="isSubmitting"
									:disabled="!canSubmit"
								/>
								<p
									class="mt-3 text-center text-ik-kicker uppercase text-ik-outline"
								>
									No charge today • Cancel before day
									{{ pricing.trial_days }}
									• Change seats anytime
								</p>
							</div>
						</form>
					</section>
				</div>

				<div class="flex flex-col gap-6 lg:col-span-5">
					<PlanSummaryCard
						:product-title="productTitle"
						:modules="product?.modules ?? []"
						:seats="seats"
						:pricing="pricing"
						:quote="quoteFor(seats)"
					/>
					<TrustProofCard :trust="onboarding.trust" />
					<SetupHelpRibbon :help="onboarding.trust.help" />
				</div>
			</div>
		</div>
	</SetupShell>
</template>
