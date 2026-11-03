<script setup lang="ts">
import { computed } from 'vue'
import SegmentedControl from '@/components/onboarding/setup/SegmentedControl.vue'
import { type InviteRow, MODULE_OPTIONS, ROLE_OPTIONS } from '@/lib/teamInvites'

export type InviteState = 'draft' | 'sending' | 'sent' | 'error'

interface MemberInviteRowProps {
	/** A unique prefix for the ids of the row's fields. */
	id: string
	state: InviteState
	/** The site's answer: a sent note, or why the row was refused. */
	message?: string
	/** A field validation message, shown under the email. */
	error?: string
	/** The workspace is not ready to send invitations yet. */
	waiting?: boolean
	removable?: boolean
}

const props = defineProps<MemberInviteRowProps>()
defineEmits<{ send: []; remove: [] }>()
const row = defineModel<InviteRow>({ required: true })

const isEmpty = computed(() => !row.value.email.trim())
const locked = computed(
	() => props.state === 'sending' || props.state === 'sent',
)
const sendLabel = computed(() => {
	if (props.state === 'sent') return 'Invited'
	if (props.state === 'sending') return 'Sending'
	return props.state === 'error' ? 'Retry' : 'Send Invite'
})
</script>

<template>
	<div
		class="flex flex-col gap-4 rounded-ik-lg bg-white p-4 shadow-ik-1 ring-1 ring-ik-line/60"
		:class="{ 'ring-ik-jade/60': state === 'sent' }"
	>
		<div class="grid grid-cols-1 gap-4 md:grid-cols-2">
			<div class="flex flex-col gap-1.5">
				<label
					:for="`${id}-name`"
					class="flex items-center justify-between text-ik-label-sm text-ik-text"
				>
					<span>Full Name</span>
					<span class="font-normal text-ik-muted">Optional</span>
				</label>
				<div class="relative flex items-center">
					<span
						class="lucide-user pointer-events-none absolute left-3.5 size-[18px] text-ik-slate"
						aria-hidden="true"
					/>
					<input
						:id="`${id}-name`"
						v-model="row.full_name"
						type="text"
						autocomplete="off"
						placeholder="e.g. Layla Al-Hassan"
						maxlength="140"
						:readonly="locked"
						class="h-12 w-full rounded-ik-md border-0 bg-ik-panel pl-10 pr-4 text-ik-body text-ik-text transition-shadow placeholder:text-ik-placeholder focus:bg-white focus:shadow-ik-focus focus:outline-none focus:ring-0 read-only:text-ik-muted"
					/>
				</div>
			</div>
			<div class="flex flex-col gap-1.5">
				<label
					:for="`${id}-email`"
					class="flex items-center justify-between text-ik-label-sm text-ik-text"
				>
					<span>Work Email</span>
					<span class="font-normal text-ik-muted"
						>Receives the activation email</span
					>
				</label>
				<div class="relative flex items-center">
					<span
						class="lucide-mail pointer-events-none absolute left-3.5 size-[18px] text-ik-slate"
						aria-hidden="true"
					/>
					<input
						:id="`${id}-email`"
						v-model="row.email"
						type="email"
						autocomplete="off"
						placeholder="colleague@company.com"
						:readonly="locked"
						:aria-invalid="Boolean(error) || undefined"
						class="h-12 w-full rounded-ik-md border-0 bg-ik-panel pl-10 pr-4 text-ik-body text-ik-text transition-shadow placeholder:text-ik-placeholder focus:bg-white focus:shadow-ik-focus focus:outline-none focus:ring-0 read-only:text-ik-muted"
						:class="{ 'shadow-ik-invalid': error }"
					/>
				</div>
				<p v-if="error" class="text-ik-body-sm text-ik-error" role="alert">
					{{ error }}
				</p>
			</div>
		</div>

		<div class="grid grid-cols-1 items-end gap-4 lg:grid-cols-12">
			<div class="flex flex-col gap-1.5 lg:col-span-6">
				<span class="text-ik-kicker uppercase text-ik-slate">
					Module Permissions
				</span>
				<SegmentedControl
					v-model="row.modules"
					label="Module permissions"
					:options="MODULE_OPTIONS"
					:disabled="locked"
				/>
			</div>
			<div class="flex flex-col gap-1.5 lg:col-span-3">
				<label
					:for="`${id}-role`"
					class="text-ik-kicker uppercase text-ik-slate"
				>
					Assigned Role
				</label>
				<div class="relative">
					<select
						:id="`${id}-role`"
						v-model="row.role"
						:disabled="locked"
						class="h-11 w-full cursor-pointer appearance-none rounded-ik-md border-0 bg-ik-panel bg-none px-3 pr-9 text-ik-label text-ik-text focus:shadow-ik-focus focus:outline-none focus:ring-0 disabled:cursor-not-allowed"
					>
						<option v-for="role in ROLE_OPTIONS" :key="role" :value="role">
							{{ role }}
						</option>
					</select>
					<span
						class="lucide-chevron-down pointer-events-none absolute right-3 top-3.5 size-4 text-ik-slate"
						aria-hidden="true"
					/>
				</div>
			</div>
			<div class="flex gap-2 lg:col-span-3">
				<button
					type="button"
					class="flex h-11 flex-1 items-center justify-center gap-1.5 rounded-ik-md px-3 text-ik-label transition-colors focus-visible:shadow-ik-focus focus-visible:outline-none disabled:cursor-not-allowed"
					:class="
						state === 'sent'
							? 'bg-ik-jade-soft text-ik-jade-ink'
							: waiting || isEmpty
								? 'bg-ik-chip text-ik-muted'
								: 'bg-ik-primary-deep text-white shadow-ik-1 hover:bg-ik-primary'
					"
					:disabled="locked || waiting"
					:title="waiting ? 'You can send invitations once your workspace is ready' : undefined"
					@click="$emit('send')"
				>
					<span
						class="size-4"
						:class="{
							'lucide-mail-check': state === 'sent',
							'lucide-loader-circle animate-spin': state === 'sending',
							'lucide-send': (state === 'draft' && !isEmpty) || state === 'error',
							'lucide-plus': state === 'draft' && isEmpty,
						}"
						aria-hidden="true"
					/>
					{{ sendLabel }}
				</button>
				<button
					v-if="removable && !locked"
					type="button"
					class="flex size-11 shrink-0 items-center justify-center rounded-ik-md text-ik-slate hover:bg-ik-chip hover:text-ik-text focus-visible:shadow-ik-focus focus-visible:outline-none"
					aria-label="Remove this member"
					@click="$emit('remove')"
				>
					<span class="lucide-trash-2 size-4" aria-hidden="true" />
				</button>
			</div>
		</div>

		<p
			v-if="message"
			class="text-ik-body-sm"
			:class="state === 'error' ? 'text-ik-error' : 'text-ik-jade-ink'"
			:role="state === 'error' ? 'alert' : 'status'"
		>
			{{ message }}
		</p>
	</div>
</template>
