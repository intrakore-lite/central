<script setup lang="ts">
interface SetupLoadErrorProps {
	message: string
}

defineProps<SetupLoadErrorProps>()
defineEmits<{ retry: [] }>()
</script>

<template>
	<div class="rounded-ik-md bg-ik-error-soft p-4" role="alert">
		<p class="text-ik-label text-ik-error">We could not open your setup</p>
		<p class="mt-1 text-ik-body-sm text-ik-text">{{ message }}</p>
		<div class="mt-3 flex flex-wrap gap-2">
			<button
				type="button"
				class="h-11 rounded-ik-md bg-white px-4 text-ik-label text-ik-ink shadow-ik-line hover:bg-ik-canvas-soft focus-visible:shadow-ik-focus focus-visible:outline-none"
				@click="$emit('retry')"
			>
				Try again
			</button>
			<a
				href="/dashboard/servers"
				class="flex h-11 items-center rounded-ik-md px-4 text-ik-label text-ik-ink hover:underline"
			>
				Open the console
			</a>
		</div>
	</div>
</template>
