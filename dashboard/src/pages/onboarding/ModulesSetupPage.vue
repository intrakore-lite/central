<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import BidWeightSliders from '@/components/onboarding/setup/BidWeightSliders.vue'
import PipelineMilestones from '@/components/onboarding/setup/PipelineMilestones.vue'
import SetupLoadError from '@/components/onboarding/setup/SetupLoadError.vue'
import SetupShell from '@/components/onboarding/setup/SetupShell.vue'
import WorkspaceProgress from '@/components/onboarding/setup/WorkspaceProgress.vue'
import { useSetupOnboarding } from '@/composables/useSetupOnboarding'
import { useWorkspaceSetup } from '@/composables/useWorkspaceSetup'
import { frappeErrorMessage } from '@/lib/auth'
import { brand } from '@/lib/brand'
import {
	CURRENCIES,
	cloneSetup,
	GCC_PRESET,
	LABOUR_RATE_BASES,
	LEAD_SOURCES,
	type MasterSetupForm,
	matchesPreset,
	NEUTRAL_SETUP,
	setupErrors,
	TEMPLATES,
	toMasterConfig,
	type UomSystem,
} from '@/lib/masterSetup'
import type { MasterSetupReport } from '@/types/onboarding'

const UOM_OPTIONS: { value: UomSystem; label: string; icon: string }[] = [
	{
		value: 'metric',
		label: 'Metric System (m, m², m³, kg)',
		icon: 'lucide-triangle-right',
	},
	{
		value: 'imperial',
		label: 'Imperial (ft, sq ft, lbs)',
		icon: 'lucide-ruler',
	},
]
// Keys the site keeps for later today (see intrakore_master NO_PLACE_YET). Shown, not refused.
const SAVED_FOR_LATER_NOTE = 'Kept with your setup; applied in a later release.'

const { team, onboarding, loading, loadError, load, resume } =
	useSetupOnboarding()
const workspace = useWorkspaceSetup(team)
const { state, stateError, isReady } = workspace

const form = ref<MasterSetupForm>(cloneSetup(GCC_PRESET))
const submitting = ref(false)
const launching = ref(false)
const retrying = ref(false)
const showErrors = ref(false)
const error = ref('')
const report = ref<MasterSetupReport | null>(null)

const presetsOn = computed(() => matchesPreset(form.value, GCC_PRESET))
const errors = computed(() => setupErrors(form.value))
const failedItems = computed(() => Object.entries(report.value?.failed ?? {}))
const skippedItems = computed(() => Object.keys(report.value?.skipped ?? {}))
const trust = computed(() => onboarding.value?.trust ?? null)
const ready = computed(() => isReady.value && !errors.value.length)
const hasCrm = computed(() => moduleIncluded('crm'))
const hasEstimation = computed(() => moduleIncluded('estim'))

function moduleIncluded(fragment: string): boolean {
	const modules = onboarding.value?.product?.modules ?? []
	return (
		!modules.length ||
		modules.some((title) => title.toLowerCase().includes(fragment))
	)
}

onMounted(async () => {
	await load()
	if (await resume(4)) return
	await workspace.follow()
})

function togglePresets(): void {
	form.value = cloneSetup(presetsOn.value ? NEUTRAL_SETUP : GCC_PRESET)
}

function toggleLeadSource(source: string): void {
	const sources = form.value.lead_sources
	form.value.lead_sources = sources.includes(source)
		? sources.filter((item) => item !== source)
		: [...sources, source]
}

function exportConfiguration(): void {
	const blob = new Blob([JSON.stringify(toMasterConfig(form.value), null, 2)], {
		type: 'application/json',
	})
	const link = document.createElement('a')
	link.href = URL.createObjectURL(blob)
	link.download = 'master-setup.json'
	link.click()
	URL.revokeObjectURL(link.href)
}

async function complete(): Promise<void> {
	if (submitting.value) return
	showErrors.value = true
	error.value = ''
	if (!isReady.value) {
		error.value = 'Your workspace is still being built. This finishes shortly.'
		return
	}
	if (errors.value.length) return
	submitting.value = true
	try {
		report.value = await workspace.applyMasterSetup(toMasterConfig(form.value))
		if (!failedItems.value.length) await launch()
	} catch (exception) {
		error.value = frappeErrorMessage(
			exception,
			'Could not apply your setup. Try again.',
		)
	} finally {
		submitting.value = false
	}
}

async function launch(): Promise<void> {
	const site = report.value?.site ?? state.value?.site?.name
	if (!site) {
		window.location.assign('/dashboard/servers')
		return
	}
	launching.value = true
	try {
		await workspace.openWorkspace(site)
	} catch (exception) {
		launching.value = false
		error.value = frappeErrorMessage(
			exception,
			'Your setup is saved, but we could not sign you in. Open your workspace from the console.',
		)
	}
}

async function retrySetup(): Promise<void> {
	retrying.value = true
	try {
		await workspace.retrySetup()
	} catch (exception) {
		error.value = frappeErrorMessage(
			exception,
			'Could not start the setup again.',
		)
	} finally {
		retrying.value = false
	}
}
</script>

<template>
	<SetupShell :step="4">
		<div class="mx-auto w-full max-w-[1360px] px-4 py-8 sm:px-8 md:py-10">
			<div
				class="mb-10 flex flex-col justify-between gap-6 lg:flex-row lg:items-end"
			>
				<div class="max-w-4xl">
					<p class="mb-3 flex items-center gap-3">
						<span
							class="rounded-full bg-ik-primary-soft px-2.5 py-1 text-ik-kicker uppercase text-ik-primary-deep"
						>
							Step 4 of 4
						</span>
						<span class="text-ik-label-sm text-ik-slate">
							Final Configuration
						</span>
					</p>
					<h1
						class="text-ik-headline-mobile font-extrabold text-ik-ink md:text-ik-display md:font-extrabold"
					>
						Master Configuration: CRM &amp; Estimation
					</h1>
					<p class="mt-2 text-ik-body-lg text-ik-slate">
						Calibrate pipeline qualification, currency standards and BOQ rate
						books for your regional contracting team.
					</p>
				</div>
				<button
					type="button"
					role="switch"
					:aria-checked="presetsOn"
					class="flex items-center gap-3 self-start rounded-ik-lg bg-white px-5 py-3 text-ik-label-lg font-bold text-ik-primary-deep shadow-ik-1 focus-visible:shadow-ik-focus focus-visible:outline-none lg:self-auto"
					@click="togglePresets"
				>
					<span class="lucide-wand-sparkles size-5" aria-hidden="true" />
					UAE / GCC Presets
					<span
						class="flex h-7 w-12 items-center rounded-full p-1 transition-colors"
						:class="presetsOn ? 'bg-ik-primary' : 'bg-ik-control'"
						aria-hidden="true"
					>
						<span
							class="size-5 rounded-full bg-white shadow-ik-1 transition-transform"
							:class="presetsOn ? 'translate-x-5' : ''"
						/>
					</span>
				</button>
			</div>

			<SetupLoadError v-if="loadError" :message="loadError" @retry="load" />

			<div
				v-else-if="loading || !onboarding"
				class="grid gap-8 lg:grid-cols-2"
				aria-busy="true"
				aria-label="Loading your setup"
			>
				<div class="h-[560px] animate-pulse rounded-ik-xl bg-white/70" />
				<div class="h-[560px] animate-pulse rounded-ik-xl bg-white/70" />
			</div>

			<template v-else>
				<WorkspaceProgress
					v-if="!isReady"
					class="mb-8"
					:state="state"
					:error="stateError"
					:retrying="retrying"
					@retry="retrySetup"
				/>

				<div class="grid grid-cols-1 items-start gap-8 lg:grid-cols-2">
					<section class="rounded-ik-xl bg-white p-6 shadow-ik-2 sm:p-10">
						<div class="mb-8 flex items-start justify-between gap-4">
							<div class="flex items-center gap-3">
								<span
									class="flex size-12 shrink-0 items-center justify-center rounded-ik-md bg-ik-primary-soft text-ik-primary"
									aria-hidden="true"
								>
									<span class="lucide-network size-6" />
								</span>
								<div>
									<h2 class="text-ik-title text-ik-ink">CRM Master Setup</h2>
									<p class="text-ik-kicker uppercase text-ik-primary-deep">
										Opportunity Pipeline &amp; Tenders
									</p>
								</div>
							</div>
							<span
								class="rounded-full bg-ik-chip px-2.5 py-1 text-ik-label-sm text-ik-slate"
							>
								{{ hasCrm ? 'Active Module' : 'Not in your plan' }}
							</span>
						</div>

						<div class="flex flex-col gap-8">
							<div class="flex flex-col gap-2">
								<div class="flex items-center justify-between">
									<span class="text-ik-label-lg text-ik-text">
										Sales Pipeline Milestones
									</span>
									<span class="text-ik-kicker uppercase text-ik-slate">
										Drag to reorder
									</span>
								</div>
								<PipelineMilestones v-model="form.pipeline_stages" />
								<p class="text-ik-label-sm text-ik-muted">
									{{ SAVED_FOR_LATER_NOTE }}
								</p>
							</div>

							<div class="flex flex-col gap-2">
								<label
									for="deal-currency"
									class="text-ik-label-lg text-ik-text"
								>
									Base Deal Currency
								</label>
								<div class="relative">
									<select
										id="deal-currency"
										v-model="form.deal_currency"
										class="h-12 w-full cursor-pointer appearance-none rounded-ik-md border-0 bg-ik-panel bg-none px-4 pr-10 text-ik-body text-ik-text focus:shadow-ik-focus focus:outline-none focus:ring-0"
									>
										<option
											v-for="currency in CURRENCIES"
											:key="currency.code"
											:value="currency.code"
										>
											{{ currency.label }}
										</option>
									</select>
									<span
										class="lucide-chevron-down pointer-events-none absolute right-4 top-4 size-4 text-ik-slate"
										aria-hidden="true"
									/>
								</div>
							</div>

							<div class="flex flex-col gap-2">
								<div class="flex items-center justify-between">
									<span class="text-ik-label-lg text-ik-text">
										Bid / No-Bid Weighted Scoring
									</span>
									<span class="text-ik-kicker uppercase text-ik-primary-deep">
										Threshold: {{ form.threshold }}% win score
									</span>
								</div>
								<BidWeightSliders
									v-model="form.bid_weights"
									v-model:threshold="form.threshold"
								/>
							</div>

							<fieldset class="flex flex-col gap-2">
								<legend class="mb-2 text-ik-label-lg text-ik-text">
									Default Lead Channel Sources
								</legend>
								<div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
									<label
										v-for="source in LEAD_SOURCES"
										:key="source"
										class="flex cursor-pointer items-center gap-3 rounded-ik-md bg-ik-panel px-3 py-2.5 text-ik-body-sm text-ik-text hover:bg-ik-chip-hover"
									>
										<input
											type="checkbox"
											:checked="form.lead_sources.includes(source)"
											class="size-4 rounded border-ik-control text-ik-primary focus:ring-ik-primary"
											@change="toggleLeadSource(source)"
										/>
										{{ source }}
									</label>
								</div>
							</fieldset>
						</div>
					</section>

					<section class="rounded-ik-xl bg-white p-6 shadow-ik-2 sm:p-10">
						<div class="mb-8 flex items-start justify-between gap-4">
							<div class="flex items-center gap-3">
								<span
									class="flex size-12 shrink-0 items-center justify-center rounded-ik-md bg-ik-jade-bright text-ik-jade-ink"
									aria-hidden="true"
								>
									<span class="lucide-calculator size-6" />
								</span>
								<div>
									<h2 class="text-ik-title text-ik-ink">
										Estimation Master Setup
									</h2>
									<p class="text-ik-kicker uppercase text-ik-primary-deep">
										BOQ Architecture &amp; Cost Indexing
									</p>
								</div>
							</div>
							<span
								class="rounded-full bg-ik-chip px-2.5 py-1 text-ik-label-sm text-ik-slate"
							>
								{{ hasEstimation ? 'Active Module' : 'Not in your plan' }}
							</span>
						</div>

						<div class="flex flex-col gap-8">
							<fieldset class="flex flex-col gap-2">
								<legend class="mb-2 text-ik-label-lg text-ik-text">
									Standard Unit of Measurement (UoM)
								</legend>
								<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
									<label
										v-for="option in UOM_OPTIONS"
										:key="option.value"
										class="flex min-h-[72px] cursor-pointer items-center gap-3 rounded-ik-lg px-4 py-3 text-ik-label-lg transition-colors focus-within:shadow-ik-focus"
										:class="
											form.uom_system === option.value
												? 'bg-ik-primary-soft text-ik-primary-deep'
												: 'bg-ik-panel text-ik-slate hover:bg-ik-chip-hover'
										"
									>
										<input
											v-model="form.uom_system"
											type="radio"
											name="uom"
											:value="option.value"
											class="sr-only"
										/>
										<span
											:class="option.icon"
											class="size-5 shrink-0"
											aria-hidden="true"
										/>
										<span class="flex-1">{{ option.label }}</span>
										<span
											v-if="form.uom_system === option.value"
											class="lucide-circle-check size-5 shrink-0"
											aria-hidden="true"
										/>
									</label>
								</div>
							</fieldset>

							<div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
								<div class="flex flex-col gap-2">
									<label for="net-margin" class="text-ik-label-lg text-ik-text">
										Target Net Margin Markup
									</label>
									<div class="relative">
										<input
											id="net-margin"
											v-model.number="form.net_margin_pct"
											type="number"
											min="0"
											max="100"
											step="0.5"
											class="h-12 w-full rounded-ik-md border-0 bg-ik-panel px-4 pr-10 text-ik-body text-ik-text focus:shadow-ik-focus focus:outline-none focus:ring-0"
										/>
										<span
											class="pointer-events-none absolute right-4 top-3 text-ik-slate"
											aria-hidden="true"
										>
											%
										</span>
									</div>
									<p class="text-ik-label-sm text-ik-primary-deep">
										Standard GCC commercial benchmark
									</p>
								</div>
								<div class="flex flex-col gap-2">
									<label for="overhead" class="text-ik-label-lg text-ik-text">
										Corporate Overhead Rate
									</label>
									<div class="relative">
										<input
											id="overhead"
											v-model.number="form.overhead_pct"
											type="number"
											min="0"
											max="100"
											step="0.5"
											class="h-12 w-full rounded-ik-md border-0 bg-ik-panel px-4 pr-10 text-ik-body text-ik-text focus:shadow-ik-focus focus:outline-none focus:ring-0"
										/>
										<span
											class="pointer-events-none absolute right-4 top-3 text-ik-slate"
											aria-hidden="true"
										>
											%
										</span>
									</div>
									<p class="text-ik-label-sm text-ik-primary-deep">
										Applied before commercial review
									</p>
								</div>
								<p class="text-ik-label-sm text-ik-muted sm:col-span-2">
									Margin and overhead are set per estimate today.
									{{ SAVED_FOR_LATER_NOTE }}
								</p>
							</div>

							<fieldset class="flex flex-col gap-2">
								<legend class="mb-2 text-ik-label-lg text-ik-text">
									Initial Rate Book &amp; BOQ Template
								</legend>
								<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
									<label
										v-for="template in TEMPLATES"
										:key="template.key"
										class="flex cursor-pointer items-start gap-3 rounded-ik-lg px-4 py-3 transition-colors focus-within:shadow-ik-focus"
										:class="
											form.template === template.key
												? 'bg-ik-primary-soft/60 ring-1 ring-ik-primary/40'
												: 'bg-ik-panel hover:bg-ik-chip-hover'
										"
									>
										<span class="flex-1">
											<span
												class="block text-ik-label-lg"
												:class="
													form.template === template.key
														? 'text-ik-primary-deep'
														: 'text-ik-text'
												"
											>
												{{ template.title }}
											</span>
											<span class="block text-ik-body-sm text-ik-slate">
												{{ template.text }}
											</span>
										</span>
										<input
											v-model="form.template"
											type="radio"
											name="template"
											:value="template.key"
											class="mt-1 size-4 border-ik-outline text-ik-primary focus:ring-ik-primary"
										/>
									</label>
								</div>
							</fieldset>

							<fieldset class="flex flex-col gap-2">
								<legend class="mb-2 text-ik-label-lg text-ik-text">
									Labor &amp; Plant Equipment Rate Base
								</legend>
								<div class="flex flex-col gap-2">
									<label
										v-for="base in LABOUR_RATE_BASES"
										:key="base.key"
										class="flex cursor-pointer items-center gap-3 rounded-ik-lg px-4 py-3 transition-colors focus-within:shadow-ik-focus"
										:class="
											form.labour_rate_base === base.key
												? 'bg-ik-primary-soft/60'
												: 'bg-ik-panel hover:bg-ik-chip-hover'
										"
									>
										<span
											class="lucide-hard-hat size-5 shrink-0 text-ik-primary-deep"
											aria-hidden="true"
										/>
										<span class="flex-1">
											<span class="block text-ik-label text-ik-text">
												{{ base.title }}
											</span>
											<span class="block text-ik-body-sm text-ik-slate">
												{{ base.text }}
											</span>
										</span>
										<input
											v-model="form.labour_rate_base"
											type="radio"
											name="labour-rate-base"
											:value="base.key"
											class="size-4 border-ik-outline text-ik-primary focus:ring-ik-primary"
										/>
									</label>
								</div>
							</fieldset>
						</div>
					</section>
				</div>

				<section
					class="mt-10 flex flex-col items-start justify-between gap-6 rounded-ik-xl bg-white p-6 shadow-ik-2 sm:p-10 lg:flex-row lg:items-center"
				>
					<div class="flex items-start gap-5">
						<span
							class="flex size-16 shrink-0 items-center justify-center rounded-ik-lg bg-ik-jade-ink text-white"
							aria-hidden="true"
						>
							<span class="lucide-badge-check size-8" />
						</span>
						<div>
							<h2
								class="flex flex-wrap items-center gap-3 text-ik-title text-ik-ink md:text-[26px] md:leading-8"
							>
								Ready to initialize {{ brand.name }} Workspace
								<span
									class="rounded-full px-2.5 py-0.5 text-ik-label-sm"
									:class="
										ready
											? 'bg-ik-jade-bright text-ik-jade-ink'
											: 'bg-ik-chip text-ik-slate'
									"
								>
									{{ ready
											? 'Checks passed'
											: isReady
												? 'Check your setup'
												: 'Workspace starting' }}
								</span>
							</h2>
							<p class="mt-1 max-w-2xl text-ik-body text-ik-slate">
								Your company workspace opens with these pipeline, currency and
								BOQ defaults. You can change all of them later.
							</p>
							<ul
								v-if="showErrors && errors.length"
								class="mt-2 text-ik-body-sm text-ik-error"
								role="alert"
							>
								<li v-for="message in errors" :key="message">{{ message }}</li>
							</ul>
						</div>
					</div>
					<div class="flex w-full flex-col gap-3 sm:flex-row lg:w-auto">
						<button
							type="button"
							class="h-14 rounded-ik-md bg-ik-chip px-6 text-ik-label-lg text-ik-text hover:bg-ik-chip-hover focus-visible:shadow-ik-focus focus-visible:outline-none"
							@click="exportConfiguration"
						>
							Export Configuration
						</button>
						<button
							type="button"
							class="group flex h-14 items-center justify-center gap-3 rounded-ik-md bg-ik-primary px-8 text-ik-label-lg font-bold text-white shadow-ik-button transition-all hover:bg-ik-primary-hover focus-visible:shadow-ik-3 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-60 lg:min-w-[320px]"
							:disabled="submitting || launching"
							:aria-busy="submitting || launching || undefined"
							@click="complete"
						>
							<span
								v-if="submitting || launching"
								class="lucide-loader-circle size-5 animate-spin"
								aria-hidden="true"
							/>
							{{ launching
									? 'Opening your workspace'
									: 'Complete Setup & Launch Workspace' }}
							<span
								v-if="!submitting && !launching"
								class="lucide-arrow-right size-5 transition-transform group-hover:translate-x-1"
								aria-hidden="true"
							/>
						</button>
					</div>
				</section>

				<div
					v-if="report && (failedItems.length || skippedItems.length)"
					class="mt-6 rounded-ik-lg bg-white p-5 shadow-ik-1"
					role="status"
				>
					<p v-if="skippedItems.length" class="text-ik-body-sm text-ik-slate">
						Saved for later: {{ skippedItems.join(', ') }}.
					</p>
					<template v-if="failedItems.length">
						<p class="mt-2 text-ik-label text-ik-error">
							Some settings were not applied:
						</p>
						<ul class="mt-1 text-ik-body-sm text-ik-text">
							<li v-for="[ key, reason ] in failedItems" :key="key">
								{{ key }}: {{ reason }}
							</li>
						</ul>
						<button
							type="button"
							class="mt-3 h-11 rounded-ik-md bg-ik-primary px-5 text-ik-label text-white hover:bg-ik-primary-hover focus-visible:shadow-ik-3 focus-visible:outline-none disabled:opacity-60"
							:disabled="launching"
							@click="launch"
						>
							Open my workspace anyway
						</button>
					</template>
				</div>

				<p
					v-if="error"
					class="mt-6 rounded-ik-md bg-ik-error-soft px-4 py-3 text-ik-body-sm text-ik-error"
					role="alert"
				>
					{{ error }}
				</p>

				<p
					v-if="trust?.setup_footer_line"
					class="mt-12 flex items-center justify-center gap-2 text-ik-label-sm text-ik-slate"
				>
					<span class="lucide-shield-check size-4" aria-hidden="true" />
					{{ trust.setup_footer_line }}
				</p>
			</template>
		</div>
	</SetupShell>
</template>
