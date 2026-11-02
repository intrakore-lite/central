<script setup lang="ts">
import { Button } from 'frappe-ui'
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AuthErrorMessage from '@/components/auth/AuthErrorMessage.vue'
import AuthShell from '@/components/auth/AuthShell.vue'
import AuthSubmitButton from '@/components/auth/AuthSubmitButton.vue'
import ProductLogo from '@/components/auth/ProductLogo.vue'
import ValidatedFormControl from '@/components/common/formComponents/ValidatedFormControl.vue'
import { useEmailSignIn } from '@/composables/useEmailSignIn'
import { useProduct } from '@/composables/useProduct'
import { emailError, frappeErrorMessage, queryString } from '@/lib/auth'
import { carriedQuery } from '@/lib/authRedirect'
import { brand, trialOffer } from '@/lib/brand'

const route = useRoute()
const router = useRouter()
const { sendCode } = useEmailSignIn()
const { product, productKey } = useProduct()

const email = ref(queryString(route.query.email))
const submitted = ref(false)
const loading = ref(false)
const error = ref('')

// A visitor without a product link gets the offered free trial as the way in.
const trialSignup = computed(() =>
	!productKey.value && trialOffer
		? {
				path: '/signup',
				query: { ...carriedQuery(route.query), product: trialOffer.product },
			}
		: null,
)

async function submit() {
	submitted.value = true
	error.value = ''
	if (emailError(email.value)) return

	loading.value = true
	try {
		await sendCode(email.value.trim())
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
			Log in to {{ brand.name }}
		</h1>
		<p class="mt-1.5 text-p-base text-ink-gray-6">
			{{ product?.subtitle || 'Welcome! Please sign in to continue.' }}
		</p>

		<form class="mt-8 space-y-4" novalidate @submit.prevent="submit">
			<ValidatedFormControl
				v-model="email"
				label="Work email"
				type="email"
				variant="outline"
				autocomplete="email"
				placeholder="name@company.com"
				v-focus
				:validator="emailError"
				:submitted="submitted"
			>
				<template #prefix>
					<span class="lucide-mail size-4 text-ink-gray-5" aria-hidden="true" />
				</template>
			</ValidatedFormControl>
			<AuthErrorMessage v-if="error" :message="error" page="Sign in" />
			<AuthSubmitButton :loading="loading">Continue</AuthSubmitButton>
		</form>

		<div v-if="trialSignup" class="mt-8 space-y-3">
			<p class="text-center text-p-sm text-ink-gray-6">New to Intrakore?</p>
			<Button variant="outline" size="md" class="w-full" :route="trialSignup">
				Start your free {{ trialOffer?.days }}-day trial
			</Button>
		</div>
		<p v-else class="mt-8 text-center text-p-sm text-ink-gray-6">
			New to {{ brand.name }}?
			<RouterLink
				class="text-p-sm-medium text-blueprint-700 hover:underline dark:text-blueprint-300"
				:to="{ path: '/signup', query: carriedQuery(route.query) }"
			>
				Create an account
			</RouterLink>
		</p>
	</AuthShell>
</template>
