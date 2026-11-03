<script setup lang="ts">
import { Button } from 'frappe-ui'
import { computed } from 'vue'
import SettingsSection from '@/components/common/SettingsSection.vue'
import type { VirtualMachineRow } from '@/composables/useServers'
import type { ServerActions } from '@/lib/capabilities'
import { features } from '@/lib/features'
import { isSettingUp } from '@/lib/status'

interface Props {
	server: VirtualMachineRow
	actions: ServerActions
}

const props = defineProps<Props>()

const emit = defineEmits<{
	resize: []
	terminate: []
}>()

const isLocked = computed(
	() => !!props.server.pending_action || isSettingUp(props.server.status),
)

const resizeCopy = features.managed
	? {
			title: 'Change plan',
			description:
				'Move this site to another plan. A plan change restarts the site for a few minutes.',
			label: 'Change plan',
		}
	: {
			title: 'Resize server',
			description:
				'Change CPU, memory, or disk size. CPU and memory changes restart the server. Disk size can only increase.',
			label: 'Resize',
		}

const terminateCopy = features.managed
	? {
			title: 'Terminate site',
			description: 'Permanently deletes the site and all its data.',
		}
	: {
			title: 'Terminate server',
			description:
				'Permanently deletes the server and its disk. Create a snapshot first to keep a backup.',
		}
</script>

<template>
	<div class="divide-y divide-outline-gray-1">
		<SettingsSection
			:title="resizeCopy.title"
			:description="resizeCopy.description"
		>
			<template v-if="actions.resize" #actions>
				<Button
					:label="resizeCopy.label"
					:disabled="isLocked"
					@click="emit('resize')"
				/>
			</template>
		</SettingsSection>

		<SettingsSection
			v-if="actions.terminate"
			:title="terminateCopy.title"
			:description="terminateCopy.description"
		>
			<template #actions>
				<Button
					theme="red"
					label="Terminate"
					:disabled="isLocked"
					@click="emit('terminate')"
				/>
			</template>
		</SettingsSection>
	</div>
</template>
