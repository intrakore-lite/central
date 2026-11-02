<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AuthErrorMessage from '@/components/auth/AuthErrorMessage.vue'
import AuthShell from '@/components/auth/AuthShell.vue'
import AuthSubmitButton from '@/components/auth/AuthSubmitButton.vue'
import ProductLogo from '@/components/auth/ProductLogo.vue'
import TermsNotice from '@/components/auth/TermsNotice.vue'
import ValidatedFormControl from '@/components/common/formComponents/ValidatedFormControl.vue'
import { useEmailSignIn } from '@/composables/useEmailSignIn'
import { useProduct } from '@/composables/useProduct'
import {
	emailError,
	frappeErrorMessage,
	queryString,
	requiredError,
} from '@/lib/auth'
import { carriedQuery } from '@/lib/authRedirect'
import { trialDays } from '@/lib/brand'

const route = useRoute()
const router = useRouter()
const { sendCode } = useEmailSignIn()
const { product, productKey } = useProduct()

const fullName = ref('')
const email = ref(queryString(route.query.email))
const submitted = ref(false)
const loading = ref(false)
const error = ref('')

const trialSummary = computed(() => {
	const days = trialDays(productKey.value)
	const trial = [days && `${days} days`, product.value?.title]
		.filter(Boolean)
		.join(' of ')
	return trial
		? `${trial}, free. No card needed to start.`
		: 'No card needed to start.'
})

async function submit() {
	submitted.value = true
	error.value = ''
	if (requiredError('Full name')(fullName.value) || emailError(email.value))
		return

	loading.value = true
	try {
		await sendCode(email.value.trim(), fullName.value.trim())
		await router.push({
			path: '/verify',
			query: { ...carriedQuery(route.query), email: email.value.trim() },
		})
	} catch (exception) {
		error.value = frappeErrorMessage(exception, 'Could not send a code.')
	} finally {
		loading.value = false
	}
}
</script>

<template>
	<AuthShell :show-progress="Boolean(productKey)" :step="1">
		<h1 class="flex items-center gap-2 text-3xl-semibold text-ink-gray-9">
			<ProductLogo />
			{{ productKey ? 'Start your free trial' : 'Create your account' }}
		</h1>
		<p
			v-if="productKey || product?.subtitle"
			class="mt-1.5 text-p-base text-ink-gray-6"
		>
			{{ productKey ? trialSummary : product?.subtitle }}
		</p>

		<form class="mt-8 space-y-4" novalidate @submit.prevent="submit">
			<ValidatedFormControl
				v-model="fullName"
				label="Full name"
				variant="outline"
				autocomplete="name"
				placeholder="Your full name"
				v-focus
				:validator="requiredError('Full name')"
				:submitted="submitted"
			>
				<template #prefix>
					<span class="lucide-user size-4 text-ink-gray-5" aria-hidden="true" />
				</template>
			</ValidatedFormControl>
			<ValidatedFormControl
				v-model="email"
				label="Work email"
				type="email"
				variant="outline"
				autocomplete="email"
				placeholder="name@company.com"
				:validator="emailError"
				:submitted="submitted"
			>
				<template #prefix>
					<span class="lucide-mail size-4 text-ink-gray-5" aria-hidden="true" />
				</template>
			</ValidatedFormControl>
			<AuthErrorMessage v-if="error" :message="error" page="Sign up" />
			<AuthSubmitButton :loading="loading">Continue</AuthSubmitButton>
		</form>

		<div class="mt-8 space-y-2 text-center text-p-sm text-ink-gray-6">
			<p>
				Already have an account?
				<RouterLink
					class="text-p-sm-medium text-blueprint-700 hover:underline dark:text-blueprint-300"
					:to="{ path: '/login', query: carriedQuery(route.query) }"
				>
					Log in
				</RouterLink>
			</p>
			<TermsNotice />
		</div>
	</AuthShell>
</template>
