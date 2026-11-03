<script setup lang="ts">
import { computed, onMounted, ref, useTemplateRef, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import MemberInviteRow, {
	type InviteState,
} from '@/components/onboarding/setup/MemberInviteRow.vue'
import SetupLoadError from '@/components/onboarding/setup/SetupLoadError.vue'
import SetupShell from '@/components/onboarding/setup/SetupShell.vue'
import WorkspaceProgress from '@/components/onboarding/setup/WorkspaceProgress.vue'
import { useMyProfile } from '@/composables/useMyProfile'
import { useSetupOnboarding } from '@/composables/useSetupOnboarding'
import { useWorkspaceSetup } from '@/composables/useWorkspaceSetup'
import { frappeErrorMessage } from '@/lib/auth'
import { carriedQuery } from '@/lib/authRedirect'
import { brand } from '@/lib/brand'
import {
	CSV_TEMPLATE,
	duplicateEmails,
	emptyRow,
	type InviteRow,
	isBlankRow,
	MAX_INVITES,
	parseMembersCsv,
	rowError,
	seatShare,
} from '@/lib/teamInvites'
import type { InviteResult } from '@/types/onboarding'

interface MemberDraft {
	key: number
	row: InviteRow
	state: InviteState
	message: string
	error: string
}

const FEATURE_ICONS = [
	'lucide-layout-grid',
	'lucide-mail-check',
	'lucide-armchair',
]

const route = useRoute()
const router = useRouter()
const { profile: myProfile } = useMyProfile()
const { team, onboarding, loading, loadError, load, resume, finishTeamStep } =
	useSetupOnboarding()
const workspace = useWorkspaceSetup(team)
const { state, stateError, isReady } = workspace
const csvInput = useTemplateRef<HTMLInputElement>('csv')

let nextKey = 1
const members = ref<MemberDraft[]>([draft(emptyRow())])
const csvErrors = ref<string[]>([])
const csvNote = ref('')
const pageError = ref('')
const continuing = ref(false)
const retrying = ref(false)

const ownerEmail = computed(() => onboarding.value?.profile.email ?? '')
const ownerName = computed(
	() => onboarding.value?.profile.full_name || myProfile.value?.full_name || '',
)
const ownerInitials = computed(() =>
	(ownerName.value || ownerEmail.value)
		.split(/\s+/)
		.filter(Boolean)
		.slice(0, 2)
		.map((word) => word[0].toUpperCase())
		.join(''),
)
const trust = computed(() => onboarding.value?.trust ?? null)
const seatCap = computed(
	() => state.value?.seats?.cap ?? onboarding.value?.profile.seats ?? null,
)
const sentCount = computed(
	() => members.value.filter((member) => member.state === 'sent').length,
)
const seatsUsed = computed(
	() => state.value?.seats?.used ?? 1 + sentCount.value,
)
const seatsPercent = computed(() => seatShare(seatsUsed.value, seatCap.value))
const pending = computed(() =>
	members.value.filter(
		(member) => member.state !== 'sent' && !isBlankRow(member.row),
	),
)

/** The planned seats by access, for the distribution bar. The owner is an admin. */
const distribution = computed(() => {
	const planned = members.value.filter((member) => !isBlankRow(member.row))
	const count = (test: (row: InviteRow) => boolean) =>
		planned.filter((member) => test(member.row)).length
	const admins = 1 + count((row) => row.role === 'Admin')
	const crm = count((row) => row.role !== 'Admin' && row.modules === 'crm')
	const estimation = count(
		(row) => row.role !== 'Admin' && row.modules === 'estimation',
	)
	const both = count((row) => row.role !== 'Admin' && row.modules === 'both')
	const total = Math.max(
		seatCap.value ?? 0,
		admins + crm + estimation + both,
		1,
	)
	return [
		{ label: 'Estimation', count: estimation, color: 'bg-ik-primary' },
		{ label: 'CRM', count: crm, color: 'bg-ik-jade-ink' },
		{ label: 'Both', count: both, color: 'bg-ik-primary-deep/40' },
		{ label: 'Admin', count: admins, color: 'bg-ik-slate' },
	].map((part) => ({ ...part, width: (part.count / total) * 100 }))
})
const distributionLabel = computed(() =>
	distribution.value.map((part) => `${part.label}: ${part.count}`).join(', '),
)

const storageKey = computed(() => `ik-team-invites:${team.value ?? ''}`)
const templateHref = `data:text/csv;charset=utf-8,${encodeURIComponent(CSV_TEMPLATE)}`

function draft(row: InviteRow): MemberDraft {
	return { key: nextKey++, row, state: 'draft', message: '', error: '' }
}

onMounted(async () => {
	await load()
	if (await resume(3)) return
	restoreDrafts()
	await workspace.follow()
})

// The rows survive a reload while the workspace is still being built.
watch(
	members,
	(value) => {
		if (!team.value) return
		const drafts = value
			.filter((member) => member.state !== 'sent' && !isBlankRow(member.row))
			.map((member) => member.row)
		if (drafts.length)
			localStorage.setItem(storageKey.value, JSON.stringify(drafts))
		else localStorage.removeItem(storageKey.value)
	},
	{ deep: true },
)

function restoreDrafts(): void {
	try {
		const saved = JSON.parse(localStorage.getItem(storageKey.value) || '[]')
		if (Array.isArray(saved) && saved.length)
			members.value = saved.map((row: InviteRow) =>
				draft({ ...emptyRow(), ...row }),
			)
	} catch {
		localStorage.removeItem(storageKey.value)
	}
}

function addMember(): void {
	if (members.value.length >= MAX_INVITES) return
	members.value.push(draft(emptyRow()))
}

function removeMember(key: number): void {
	members.value = members.value.filter((member) => member.key !== key)
	if (!members.value.length) addMember()
}

/** Check the rows to send. True when each one can go. */
function validate(targets: MemberDraft[]): boolean {
	const duplicates = duplicateEmails(members.value.map((member) => member.row))
	let valid = true
	for (const member of targets) {
		const email = member.row.email.trim().toLowerCase()
		member.error =
			rowError(member.row, ownerEmail.value) ||
			(duplicates.has(email) ? 'This email is in another row.' : '')
		if (member.error) valid = false
	}
	return valid
}

async function send(targets: MemberDraft[]): Promise<boolean> {
	if (!targets.length || !validate(targets) || !isReady.value) return false
	for (const member of targets) {
		member.state = 'sending'
		member.message = ''
	}
	try {
		const answer = await workspace.invite(targets.map((member) => member.row))
		const byEmail = new Map(
			answer.results.map((result) => [result.email, result]),
		)
		for (const member of targets)
			record(member, byEmail.get(member.row.email.trim().toLowerCase()))
	} catch (exception) {
		const message = frappeErrorMessage(
			exception,
			'Could not send the invitation.',
		)
		for (const member of targets) {
			member.state = 'error'
			member.message = message
		}
	}
	return targets.every((member) => member.state === 'sent')
}

function record(member: MemberDraft, result: InviteResult | undefined): void {
	if (!result || result.status === 'error') {
		member.state = 'error'
		member.message =
			result?.error || 'Your workspace did not accept this member.'
		return
	}
	member.state = 'sent'
	const missing = result.missing_roles?.length
		? ` Some roles are not in your plan: ${result.missing_roles.join(', ')}.`
		: ''
	member.message = result.email_sent
		? `Activation email sent to ${result.email}.${missing}`
		: `${result.email} already has access.${missing}`
}

function openCsv(): void {
	csvInput.value?.click()
}

async function importCsv(event: Event): Promise<void> {
	const input = event.target as HTMLInputElement
	const file = input.files?.[0]
	input.value = ''
	if (!file) return
	const { rows, errors } = parseMembersCsv(await file.text())
	csvErrors.value = errors
	const known = new Set(
		members.value.map((member) => member.row.email.trim().toLowerCase()),
	)
	const fresh = rows.filter((row) => !known.has(row.email))
	members.value = [
		...members.value.filter(
			(member) => member.state === 'sent' || !isBlankRow(member.row),
		),
		...fresh.map(draft),
	].slice(0, MAX_INVITES)
	if (!members.value.length) addMember()
	csvNote.value = `${fresh.length} member${fresh.length === 1 ? '' : 's'} imported from ${file.name}.`
}

function resetRows(): void {
	members.value = [
		...members.value.filter((member) => member.state === 'sent'),
		draft(emptyRow()),
	]
	csvErrors.value = []
	csvNote.value = ''
}

async function retrySetup(): Promise<void> {
	retrying.value = true
	try {
		await workspace.retrySetup()
	} catch (exception) {
		pageError.value = frappeErrorMessage(
			exception,
			'Could not start the setup again.',
		)
	} finally {
		retrying.value = false
	}
}

async function leave(sendPending: boolean): Promise<void> {
	if (continuing.value) return
	pageError.value = ''
	continuing.value = true
	try {
		if (sendPending && pending.value.length) {
			if (!isReady.value) {
				pageError.value =
					'Your workspace is still being built. Send the invitations when it is ready, or skip for now.'
				return
			}
			if (!(await send(pending.value))) {
				pageError.value =
					'Some invitations were not sent. Fix them or remove them.'
				return
			}
		}
		await finishTeamStep()
		await router.push({
			path: '/onboarding/modules-setup',
			query: carriedQuery(route.query),
		})
	} catch (exception) {
		pageError.value = frappeErrorMessage(
			exception,
			'Could not save this step. Try again.',
		)
	} finally {
		continuing.value = false
	}
}
</script>

<template>
	<SetupShell :step="3">
		<div class="mx-auto w-full max-w-[1360px] px-4 py-8 sm:px-8 md:py-10">
			<div class="mb-8 flex flex-wrap items-center justify-between gap-4">
				<div
					class="flex items-center gap-2 rounded-full bg-ik-panel px-4 py-1.5 shadow-ik-1"
				>
					<span
						class="size-2.5 animate-pulse rounded-full bg-ik-primary"
						aria-hidden="true"
					/>
					<span class="text-ik-kicker uppercase text-ik-primary">
						Step 3 of 4
					</span>
					<span class="text-ik-label-sm text-ik-outline" aria-hidden="true">
						/
					</span>
					<span class="text-ik-label-sm text-ik-slate">
						Access Control &amp; Provisioning
					</span>
				</div>
				<div
					v-if="trust?.team_badge"
					class="flex items-center gap-2 text-ik-label-sm text-ik-slate"
				>
					<span
						class="lucide-shield-check size-4 text-ik-primary"
						aria-hidden="true"
					/>
					{{ trust.team_badge }}
				</div>
			</div>

			<SetupLoadError v-if="loadError" :message="loadError" @retry="load" />

			<div
				v-else-if="loading || !onboarding"
				class="grid gap-6 lg:grid-cols-12"
				aria-busy="true"
				aria-label="Loading your team"
			>
				<div
					class="h-96 animate-pulse rounded-ik-xl bg-white/70 lg:col-span-8"
				/>
				<div
					class="h-96 animate-pulse rounded-ik-xl bg-white/70 lg:col-span-4"
				/>
			</div>

			<div v-else class="grid grid-cols-1 items-start gap-8 lg:grid-cols-12">
				<div class="flex flex-col gap-6 lg:col-span-8">
					<div class="flex flex-col gap-2">
						<p
							class="flex items-center gap-1.5 text-ik-kicker uppercase text-ik-primary"
						>
							<span class="lucide-user-plus size-4" aria-hidden="true" />
							Workspace Team Provisioning
						</p>
						<h1
							class="text-ik-headline-mobile font-extrabold text-ik-ink md:text-ik-display md:font-extrabold"
						>
							Add your team members
						</h1>
						<p class="max-w-2xl text-ik-body-lg text-ik-slate">
							Assign module access to CRM and Estimation. Each invited member
							receives an activation email from your workspace to set a password
							and sign in.
						</p>
					</div>

					<WorkspaceProgress
						v-if="!isReady"
						:state="state"
						:error="stateError"
						:retrying="retrying"
						@retry="retrySetup"
					/>

					<section class="overflow-hidden rounded-ik-xl bg-white shadow-ik-2">
						<div
							class="flex flex-wrap items-center justify-between gap-4 bg-ik-canvas-soft px-6 py-4"
						>
							<div class="flex flex-wrap items-center gap-3">
								<h2 class="text-ik-label-lg font-bold text-ik-text">
									Team Access Matrix
								</h2>
								<span
									class="rounded-full bg-ik-primary-soft px-2.5 py-0.5 text-ik-label-sm text-ik-primary-deep"
									aria-live="polite"
								>
									<template v-if="seatCap">
										{{ seatsUsed }}
										of {{ seatCap }} seats used
									</template>
									<template v-else>{{ seatsUsed }} seats used</template>
								</span>
							</div>
							<div class="flex items-center gap-2">
								<button
									type="button"
									class="flex h-9 items-center gap-1.5 rounded-ik-sm bg-white px-3 text-ik-label-sm text-ik-text shadow-ik-1 hover:bg-ik-panel focus-visible:shadow-ik-focus focus-visible:outline-none"
									@click="openCsv"
								>
									<span
										class="lucide-file-up size-4 text-ik-primary"
										aria-hidden="true"
									/>
									Bulk import via CSV
								</button>
								<input
									ref="csv"
									type="file"
									accept=".csv,text/csv"
									class="hidden"
									aria-label="CSV file of members"
									@change="importCsv"
								/>
								<button
									type="button"
									class="flex size-9 items-center justify-center rounded-ik-sm text-ik-slate hover:bg-ik-panel hover:text-ik-text focus-visible:shadow-ik-focus focus-visible:outline-none"
									aria-label="Clear the rows not sent"
									title="Clear the rows not sent"
									@click="resetRows"
								>
									<span class="lucide-rotate-ccw size-4" aria-hidden="true" />
								</button>
							</div>
						</div>

						<div class="flex flex-col gap-4 p-6">
							<div
								v-if="csvNote || csvErrors.length"
								class="rounded-ik-md bg-ik-panel px-4 py-3 text-ik-body-sm text-ik-text"
								role="status"
							>
								<p>{{ csvNote }}</p>
								<p v-if="csvErrors.length" class="text-ik-error">
									{{ csvErrors.slice(0, 3).join(' ') }}
									<template v-if="csvErrors.length > 3">
										{{ csvErrors.length - 3 }}
										more lines were skipped.
									</template>
								</p>
								<p class="mt-1 text-ik-label-sm text-ik-muted">
									Columns: name, email, modules (crm, estimation or both), role.
									<a
										:href="templateHref"
										download="team-members.csv"
										class="text-ik-primary underline"
									>
										Download a template
									</a>
								</p>
							</div>

							<div
								class="flex flex-col items-start justify-between gap-4 rounded-ik-lg bg-ik-panel/70 p-4 xl:flex-row xl:items-center"
							>
								<div class="flex min-w-[240px] items-center gap-3">
									<span
										class="relative flex size-11 shrink-0 items-center justify-center rounded-full bg-ik-primary-soft text-ik-label text-ik-primary"
										aria-hidden="true"
									>
										{{ ownerInitials }}
										<span
											class="absolute -bottom-0.5 -right-0.5 flex size-4 items-center justify-center rounded-full bg-ik-primary text-white"
										>
											<span class="lucide-shield size-2.5" />
										</span>
									</span>
									<div class="flex min-w-0 flex-col">
										<span class="flex items-center gap-1.5">
											<span class="truncate text-ik-label text-ik-text">
												{{ ownerName || 'Account owner' }}
											</span>
											<span
												class="rounded-full bg-ik-primary-soft px-2 py-0.5 text-[11px] font-bold uppercase text-ik-primary-deep"
											>
												You
											</span>
										</span>
										<span class="truncate text-ik-body-sm text-ik-slate">
											{{ ownerEmail }}
										</span>
									</div>
								</div>
								<div
									class="flex items-center gap-1.5 rounded-ik-sm bg-white px-3 py-1.5 shadow-ik-1"
								>
									<span
										class="lucide-circle-check size-4 text-ik-jade-ink"
										aria-hidden="true"
									/>
									<span class="text-ik-label-sm text-ik-text">
										CRM &amp; Estimation Full Access
									</span>
									<span class="text-ik-label-sm font-normal text-ik-muted">
										(Owner)
									</span>
								</div>
								<div
									class="flex w-full items-center justify-between gap-6 xl:w-auto"
								>
									<div class="flex flex-col xl:items-end">
										<span
											class="whitespace-nowrap text-ik-kicker uppercase text-ik-slate"
										>
											Workspace Role
										</span>
										<span class="text-ik-label-sm text-ik-text">
											Account Owner
										</span>
									</div>
									<span
										class="flex items-center gap-1 rounded-full bg-ik-jade-soft px-2.5 py-1 text-ik-label-sm text-ik-jade-ink"
									>
										<span class="lucide-lock size-3.5" aria-hidden="true" />
										Primary
									</span>
								</div>
							</div>

							<MemberInviteRow
								v-for="member in members"
								:id="`member-${member.key}`"
								:key="member.key"
								v-model="member.row"
								:state="member.state"
								:message="member.message"
								:error="member.error"
								:waiting="!isReady"
								:removable="members.length > 1 || !isBlankRow(member.row)"
								@send="send([member])"
								@remove="removeMember(member.key)"
							/>

							<div
								class="flex flex-col items-start justify-between gap-3 pt-2 sm:flex-row sm:items-center"
							>
								<button
									type="button"
									class="flex h-11 items-center gap-2 rounded-ik-md bg-ik-panel px-4 text-ik-label-lg font-bold text-ik-primary hover:bg-ik-primary-soft focus-visible:shadow-ik-focus focus-visible:outline-none disabled:opacity-60"
									:disabled="members.length >= MAX_INVITES"
									@click="addMember"
								>
									<span class="lucide-user-plus size-5" aria-hidden="true" />
									Add another member
								</button>
								<p class="text-ik-body-sm text-ik-slate">
									Invited members will receive an activation email.
								</p>
							</div>
						</div>
					</section>

					<section class="flex gap-4 rounded-ik-lg bg-white p-5 shadow-ik-1">
						<span
							class="flex size-11 shrink-0 items-center justify-center rounded-ik-md bg-ik-primary-soft text-ik-primary"
							aria-hidden="true"
						>
							<span class="lucide-info size-5" />
						</span>
						<div>
							<p class="text-ik-label text-ik-text">Need more seats later?</p>
							<p class="text-ik-body-sm text-ik-slate">
								Each active member uses one seat. You can change your seat count
								later from Billing in the console.
							</p>
						</div>
					</section>

					<p
						v-if="pageError"
						class="rounded-ik-md bg-ik-error-soft px-4 py-3 text-ik-body-sm text-ik-error"
						role="alert"
					>
						{{ pageError }}
					</p>

					<div
						class="flex flex-col-reverse items-stretch justify-between gap-4 pt-2 sm:flex-row sm:items-center"
					>
						<button
							type="button"
							class="flex h-12 items-center justify-center gap-2 rounded-ik-md px-2 text-ik-label-lg text-ik-slate hover:text-ik-text focus-visible:shadow-ik-focus focus-visible:outline-none"
							:disabled="continuing"
							@click="leave(false)"
						>
							<span class="lucide-arrow-left size-5" aria-hidden="true" />
							Skip for now
						</button>
						<button
							type="button"
							class="group flex h-14 items-center justify-center gap-2 rounded-ik-md bg-ik-primary px-8 text-ik-label-lg font-bold text-white shadow-ik-button transition-all hover:bg-ik-primary-hover focus-visible:shadow-ik-3 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-60 sm:min-w-[380px]"
							:disabled="continuing"
							:aria-busy="continuing || undefined"
							@click="leave(true)"
						>
							Save &amp; Continue to Master Setup
							<span
								class="lucide-arrow-right size-5 transition-transform group-hover:translate-x-1"
								aria-hidden="true"
							/>
						</button>
					</div>
				</div>

				<aside class="flex flex-col gap-6 lg:col-span-4">
					<section class="rounded-ik-xl bg-white p-6 shadow-ik-2">
						<div class="mb-3 flex items-center justify-between">
							<span class="text-ik-kicker uppercase text-ik-slate">
								Access Distribution
							</span>
							<span
								class="rounded-full bg-ik-jade-bright px-2.5 py-0.5 text-ik-label-sm text-ik-jade-ink"
							>
								{{ isReady ? 'Live' : 'Planned' }}
							</span>
						</div>
						<h2 class="mb-5 text-ik-title text-ik-ink">
							Role Permission Topology
						</h2>
						<div class="rounded-ik-lg bg-ik-panel p-4">
							<div class="mb-3 flex items-center justify-between">
								<span class="text-ik-label-sm text-ik-text">Seat usage</span>
								<span class="text-ik-label-sm text-ik-primary">
									{{ seatsPercent }}% used
								</span>
							</div>
							<div
								class="flex h-2.5 overflow-hidden rounded-full bg-ik-line"
								role="img"
								:aria-label="distributionLabel"
							>
								<div
									v-for="part in distribution"
									:key="part.label"
									:class="part.color"
									:style="{ width: `${part.width}%` }"
								/>
							</div>
							<ul
								class="mt-3 grid grid-cols-2 gap-2 text-ik-label-sm text-ik-slate"
							>
								<li
									v-for="part in distribution"
									:key="part.label"
									class="flex items-center gap-1.5"
								>
									<span
										class="size-2 rounded-full"
										:class="part.color"
										aria-hidden="true"
									/>
									{{ part.label }}
									· {{ part.count }}
								</li>
							</ul>
						</div>
						<ul v-if="trust?.team_features.length" class="mt-5 space-y-4">
							<li
								v-for="(feature, index) in trust.team_features"
								:key="feature.title"
								class="flex gap-3"
							>
								<span
									class="mt-0.5 size-5 shrink-0 text-ik-primary"
									:class="FEATURE_ICONS[index % FEATURE_ICONS.length]"
									aria-hidden="true"
								/>
								<div>
									<p class="text-ik-label text-ik-text">{{ feature.title }}</p>
									<p class="text-ik-body-sm text-ik-slate">
										{{ feature.text }}
									</p>
								</div>
							</li>
						</ul>
					</section>

					<section class="rounded-ik-xl bg-ik-panel p-6 shadow-ik-1">
						<p
							class="mb-4 flex items-center gap-2 text-ik-kicker uppercase text-ik-primary"
						>
							<span class="lucide-blocks size-4" aria-hidden="true" />
							{{ onboarding.product?.title ?? brand.name }}
						</p>
						<div
							v-if="trust?.team_stat"
							class="mb-4 rounded-ik-lg bg-white p-4 shadow-ik-1"
						>
							<p class="text-ik-kicker uppercase text-ik-slate">
								{{ trust.team_stat.label }}
							</p>
							<p class="mt-1 text-ik-headline text-ik-ink">
								{{ trust.team_stat.value }}
							</p>
							<p
								v-if="trust.team_stat.note"
								class="text-ik-body-sm text-ik-slate"
							>
								{{ trust.team_stat.note }}
							</p>
						</div>
						<div class="rounded-ik-lg bg-white p-4 shadow-ik-1">
							<p class="text-ik-kicker uppercase text-ik-slate">
								Included in your plan
							</p>
							<ul class="mt-2 flex flex-wrap gap-1.5">
								<li
									v-for="module in onboarding.product?.modules ?? []"
									:key="module"
									class="rounded-full bg-ik-primary-soft/70 px-2.5 py-1 text-ik-label-sm text-ik-primary-deep"
								>
									{{ module }}
								</li>
							</ul>
							<p
								v-if="state?.company"
								class="mt-3 text-ik-body-sm text-ik-slate"
							>
								Company:
								<span class="text-ik-text">{{ state.company }}</span>
							</p>
						</div>
						<p
							v-if="trust?.team_caption"
							class="mt-4 flex items-center gap-2 text-ik-label-sm text-ik-text"
						>
							<span
								class="lucide-badge-check size-4 text-ik-primary"
								aria-hidden="true"
							/>
							{{ trust.team_caption }}
						</p>
					</section>
				</aside>
			</div>
		</div>
	</SetupShell>
</template>
