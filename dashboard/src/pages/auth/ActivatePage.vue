<script setup lang="ts">
import { Button, ErrorMessage, LoadingText } from 'frappe-ui'
import { useRoute } from 'vue-router'
import AuthShell from '@/components/auth/AuthShell.vue'
import TermsNotice from '@/components/auth/TermsNotice.vue'
import { useAuth } from '@/composables/useAuth'
import { useTrialActivation } from '@/composables/useTrialActivation'
import { queryString } from '@/lib/auth'
import { brand } from '@/lib/brand'
import { formatDate } from '@/lib/format'

const route = useRoute()
const { currentUser } = useAuth()
const {
	activation,
	step,
	loadError,
	signInPath,
	busy,
	error,
	activate,
	switchAccount,
} = useTrialActivation(queryString(route.query.token))
</script>

<template>
	<AuthShell>
		<LoadingText v-if="step === 'loading'" text="Loading your invitation" />

		<template v-else-if="step === 'invalid'">
			<h1 class="text-2xl font-semibold text-ink-gray-9">
				This link does not work
			</h1>
			<p class="mt-1 text-p-base text-ink-gray-5">{{ loadError }}</p>
			<Button
				class="mt-8 w-full"
				size="md"
				route="/login"
				label="Go to sign in"
			/>
		</template>

		<template v-else-if="activation">
			<h1 class="text-2xl font-semibold text-ink-gray-9">
				Welcome to {{ brand.name }}
			</h1>
			<p class="mt-1 text-p-base text-ink-gray-5">
				You are invited as
				<span class="font-medium text-ink-gray-8">{{ activation.email }}</span>
				for {{ activation.company }}.
			</p>

			<div class="mt-8 space-y-4">
				<template v-if="step === 'expired'">
					<p class="text-p-base text-ink-gray-7">
						This invitation has expired. Ask your Intrakore contact to send it
						again.
					</p>
					<Button
						class="w-full"
						size="md"
						route="/login"
						label="Go to sign in"
					/>
				</template>

				<template v-else-if="step === 'wrong-account'">
					<p class="text-p-base text-ink-gray-7">
						You are signed in as {{ currentUser }}. Sign out, then open the link
						again to continue as {{ activation.email }}.
					</p>
					<ErrorMessage v-if="error" :message="error" />
					<Button
						class="w-full"
						size="md"
						variant="solid"
						label="Sign out"
						:loading="busy"
						@click="switchAccount"
					/>
				</template>

				<template v-else-if="step === 'sign-in'">
					<p class="text-p-base text-ink-gray-7">
						You already have an account. Sign in to continue.
					</p>
					<Button
						class="w-full"
						size="md"
						variant="solid"
						:route="signInPath"
						label="Sign in to continue"
					/>
				</template>

				<template v-else>
					<ErrorMessage v-if="error" :message="error" />
					<Button
						class="w-full"
						size="md"
						variant="solid"
						label="Activate your account"
						:loading="busy"
						@click="activate"
					/>
					<p class="text-center text-p-sm text-ink-gray-5">
						The link works once. It expires
						{{ formatDate(activation.expires_on) }}.
					</p>
					<TermsNotice />
				</template>
			</div>
		</template>
	</AuthShell>
</template>
