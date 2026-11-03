<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ChoiceChips from '@/components/onboarding/setup/ChoiceChips.vue'
import ProfileShowcase from '@/components/onboarding/setup/ProfileShowcase.vue'
import SeatCounter from '@/components/onboarding/setup/SeatCounter.vue'
import SetupField from '@/components/onboarding/setup/SetupField.vue'
import SetupLoadError from '@/components/onboarding/setup/SetupLoadError.vue'
import SetupSelect from '@/components/onboarding/setup/SetupSelect.vue'
import SetupShell from '@/components/onboarding/setup/SetupShell.vue'
import SetupSubmitButton from '@/components/onboarding/setup/SetupSubmitButton.vue'
import SetupTextInput from '@/components/onboarding/setup/SetupTextInput.vue'
import { useAuth } from '@/composables/useAuth'
import { useSetupOnboarding } from '@/composables/useSetupOnboarding'
import { frappeErrorMessage } from '@/lib/auth'
import { carriedQuery } from '@/lib/authRedirect'
import { brand } from '@/lib/brand'
import { DIAL_CODES, joinMobile, splitMobile } from '@/lib/dialCodes'

const route = useRoute()
const router = useRouter()
const { currentUser, logout } = useAuth()
const { onboarding, pricing, loading, loadError, load, quoteFor, saveProfile } =
	useSetupOnboarding()

const form = reactive({
	full_name: '',
	dial: DIAL_CODES[0].code,
	mobile: '',
	organisation: '',
	business_type: '',
	headcount_bracket: '',
	turnover_band: '',
	seats: 5,
})
const submitted = ref(false)
const saving = ref(false)
const saveError = ref('')

const dialCode = computed(
	() => DIAL_CODES.find((entry) => entry.code === form.dial) ?? DIAL_CODES[0],
)
const errors = computed(() => {
	if (!submitted.value) return {}
	return {
		full_name: form.full_name.trim() ? '' : 'Enter your full name.',
		mobile: joinMobile(dialCode.value, form.mobile)
			? ''
			: 'Enter your mobile number.',
		organisation: form.organisation.trim()
			? ''
			: 'Enter the legal name of your organisation.',
		business_type: form.business_type
			? ''
			: 'Choose a business classification.',
		headcount_bracket: form.headcount_bracket
			? ''
			: 'Choose a headcount bracket.',
	}
})
const hasErrors = computed(() => Object.values(errors.value).some(Boolean))

onMounted(async () => {
	await load()
	const profile = onboarding.value?.profile
	if (!profile) return
	const mobile = splitMobile(profile.mobile)
	Object.assign(form, {
		full_name: profile.full_name,
		dial: mobile.dial.code,
		mobile: mobile.number,
		organisation: profile.organisation,
		business_type: profile.business_type,
		headcount_bracket: profile.headcount_bracket,
		turnover_band: profile.turnover_band,
		seats: profile.seats || pricing.value?.included_seats || 5,
	})
})

async function submit() {
	submitted.value = true
	saveError.value = ''
	if (hasErrors.value) return
	saving.value = true
	try {
		await saveProfile({
			full_name: form.full_name,
			mobile: joinMobile(dialCode.value, form.mobile),
			country: dialCode.value.country,
			organisation: form.organisation,
			business_type: form.business_type,
			headcount_bracket: form.headcount_bracket,
			turnover_band: form.turnover_band,
			seats: form.seats,
		})
		await router.push({
			path: '/onboarding/billing',
			query: carriedQuery(route.query),
		})
	} catch (exception) {
		saveError.value = frappeErrorMessage(
			exception,
			'Could not save your details. Try again.',
		)
	} finally {
		saving.value = false
	}
}

async function signOut() {
	await logout()
	window.location.replace('/dashboard/login')
}
</script>

<template>
	<SetupShell :step="1">
		<section
			class="flex min-h-[calc(100vh-4rem)] w-full flex-col bg-white lg:flex-row"
		>
			<div
				class="flex w-full flex-col justify-between px-4 py-8 sm:px-12 md:px-16 lg:w-1/2 xl:px-24"
			>
				<div class="mx-auto flex w-full max-w-xl flex-col">
					<div class="mb-6 flex flex-wrap items-center gap-2">
						<span
							class="rounded-full bg-ik-primary-soft px-2.5 py-1 text-ik-kicker uppercase text-ik-primary"
						>
							Step 1 of 4 • Account Activation
						</span>
						<span
							v-if="onboarding?.trust.profile_badge"
							class="inline-flex items-center gap-1 text-ik-label-sm text-ik-jade-ink"
						>
							<span class="lucide-badge-check size-4" aria-hidden="true" />
							{{ onboarding.trust.profile_badge }}
						</span>
					</div>

					<h1
						class="mb-2 text-ik-headline-mobile font-extrabold text-ik-ink md:text-ik-headline md:font-extrabold"
					>
						Complete your {{ brand.name }} setup
					</h1>
					<p class="mb-8 text-ik-body text-ik-muted">
						Activate your workspace for commercial estimating, BOQ rate books,
						and GCC tender governance.
					</p>

					<div
						v-if="loading"
						class="space-y-5"
						aria-busy="true"
						aria-label="Loading your setup"
					>
						<div
							v-for="row in 5"
							:key="row"
							class="h-12 animate-pulse rounded-ik-md bg-ik-chip"
						/>
					</div>

					<SetupLoadError
						v-else-if="loadError"
						:message="loadError"
						@retry="load"
					/>

					<form
						v-else-if="onboarding && pricing"
						class="space-y-5"
						novalidate
						@submit.prevent="submit"
					>
						<div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
							<SetupField
								for="full-name"
								label="Full Name"
								:error="errors.full_name"
							>
								<template #aside>
									<span class="text-ik-label-sm text-ik-muted">
										Admin Contact
									</span>
								</template>
								<SetupTextInput
									id="full-name"
									v-model="form.full_name"
									icon="lucide-user"
									placeholder="e.g. Tariq Al-Mansoor"
									autocomplete="name"
									:invalid="Boolean(errors.full_name)"
								/>
							</SetupField>
							<SetupField for="work-email" label="Work Email">
								<template #aside>
									<span
										class="inline-flex items-center gap-0.5 text-ik-label-sm text-ik-jade-ink"
									>
										<span
											class="lucide-circle-check size-3.5"
											aria-hidden="true"
										/>
										Verified
									</span>
								</template>
								<SetupTextInput
									id="work-email"
									:model-value="onboarding.profile.email"
									icon="lucide-mail"
									type="email"
									readonly
								/>
							</SetupField>
						</div>

						<SetupField
							for="mobile"
							label="Commercial Mobile Number"
							:error="errors.mobile"
						>
							<div
								class="flex overflow-hidden rounded-ik-md shadow-ik-control focus-within:shadow-ik-focus"
								:class="{ 'shadow-ik-invalid': errors.mobile }"
							>
								<div class="relative flex items-center bg-ik-panel">
									<label for="dial-code" class="sr-only">Country code</label>
									<select
										id="dial-code"
										v-model="form.dial"
										class="h-12 cursor-pointer appearance-none border-0 bg-transparent bg-none pl-3.5 pr-8 text-ik-label text-ik-text focus:outline-none focus:ring-0"
									>
										<option
											v-for="entry in DIAL_CODES"
											:key="entry.code"
											:value="entry.code"
										>
											{{ entry.flag }} {{ entry.code }}
										</option>
									</select>
									<span
										class="lucide-chevron-down pointer-events-none absolute right-2.5 size-4 text-ik-slate"
										aria-hidden="true"
									/>
								</div>
								<input
									id="mobile"
									v-model="form.mobile"
									type="tel"
									inputmode="tel"
									autocomplete="tel-national"
									placeholder="50 000 0000"
									:aria-invalid="Boolean(errors.mobile) || undefined"
									class="h-12 w-full border-0 bg-white px-3.5 text-ik-body text-ik-text placeholder:text-ik-placeholder focus:outline-none focus:ring-0"
								/>
							</div>
						</SetupField>

						<div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
							<SetupField
								for="organisation"
								label="Organization Legal Name"
								:error="errors.organisation"
							>
								<SetupTextInput
									id="organisation"
									v-model="form.organisation"
									icon="lucide-building-2"
									placeholder="Apex Contracting LLC"
									autocomplete="organization"
									:invalid="Boolean(errors.organisation)"
								/>
							</SetupField>
							<SetupField
								for="business-type"
								label="Business Classification"
								:error="errors.business_type"
							>
								<SetupSelect
									id="business-type"
									v-model="form.business_type"
									icon="lucide-hard-hat"
									placeholder="Choose one"
									:options="onboarding.options.business_type"
									:invalid="Boolean(errors.business_type)"
								/>
							</SetupField>
						</div>

						<SetupField
							label="Employee Headcount Bracket"
							:error="errors.headcount_bracket"
						>
							<template #aside>
								<span class="text-ik-label-sm text-ik-muted">
									Permanent &amp; Site Staff
								</span>
							</template>
							<ChoiceChips
								v-model="form.headcount_bracket"
								label="Employee headcount bracket"
								:options="onboarding.options.headcount_bracket"
								:invalid="Boolean(errors.headcount_bracket)"
							/>
						</SetupField>

						<SetupField label="Annual Turnover (AED)">
							<template #aside>
								<span class="text-ik-label-sm text-ik-muted">Optional</span>
							</template>
							<ChoiceChips
								v-model="form.turnover_band"
								label="Annual turnover in AED, optional"
								:options="onboarding.options.turnover_band"
								clearable
							/>
						</SetupField>

						<SeatCounter
							v-model="form.seats"
							:product-title="onboarding.product?.title ?? brand.name"
							:pricing="pricing"
							:quote="quoteFor(form.seats)"
						/>

						<p
							v-if="saveError"
							class="rounded-ik-md bg-ik-error-soft px-4 py-3 text-ik-body-sm text-ik-error"
							role="alert"
						>
							{{ saveError }}
						</p>

						<div class="pt-2">
							<SetupSubmitButton
								label="Continue to Billing & Trial Setup"
								:loading="saving"
							/>
						</div>

						<p class="pt-2 text-center">
							<span class="text-ik-body-sm text-ik-muted">
								Not {{ currentUser }}?
							</span>
							<button
								type="button"
								class="ml-1 text-ik-label text-ik-primary hover:underline focus-visible:underline focus-visible:outline-none"
								@click="signOut"
							>
								Sign out
							</button>
						</p>
					</form>
				</div>

				<div
					v-if="onboarding"
					class="mx-auto flex w-full max-w-xl flex-wrap items-center justify-between gap-4 pt-8 text-ik-label-sm text-ik-muted"
				>
					<span
						v-for="(line, index) in onboarding.trust.profile_footer"
						:key="line"
						class="flex items-center gap-2"
					>
						<span
							class="size-4"
							:class="
								index === 0
									? 'lucide-lock text-ik-primary'
									: 'lucide-shield-check text-ik-jade-ink'
							"
							aria-hidden="true"
						/>
						{{ line }}
					</span>
				</div>
			</div>

			<ProfileShowcase
				:product-title="onboarding?.product?.title ?? null"
				:trust="onboarding?.trust ?? null"
			/>
		</section>
	</SetupShell>
</template>
