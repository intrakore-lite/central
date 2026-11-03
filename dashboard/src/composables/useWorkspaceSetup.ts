import { computed, onBeforeUnmount, type Ref, ref } from 'vue'
import { API } from '@/api/methods'
import { frappeErrorMessage, methodUrl, postFrappe } from '@/lib/auth'
import type { MasterSetupConfig } from '@/lib/masterSetup'
import type { InviteRow } from '@/lib/teamInvites'
import type {
	InviteResponse,
	MasterSetupReport,
	SiteSetupState,
} from '@/types/onboarding'

// A site takes minutes to build; a poll every few seconds shows progress without load.
const POLL_MS = 4000
const SLOW_POLL_MS = 15000
// Signing in waits for the site to mint a session, like the console's Open site.
const LOGIN_ATTEMPTS = 20
const LOGIN_RETRY_MS = 3000

interface SiteLogin {
	login_url: string | null
}

/** Onboarding steps 3 and 4: the team's own workspace, followed until it is ready,
 *  and the calls Central forwards to it. */
export function useWorkspaceSetup(team: Ref<string | null | undefined>) {
	const state = ref<SiteSetupState | null>(null)
	const stateError = ref('')
	let timer: ReturnType<typeof setTimeout> | undefined
	let stopped = false

	const isReady = computed(() => state.value?.stage === 'ready')

	async function refresh(): Promise<void> {
		try {
			state.value = await postFrappe<SiteSetupState>(
				methodUrl(API.onboardingSiteState),
				{ team: team.value },
			)
			stateError.value = ''
		} catch (exception) {
			stateError.value = frappeErrorMessage(
				exception,
				'Could not read the progress of your workspace.',
			)
		}
	}

	/** Poll until the workspace is ready. A failed one is still checked now and then. */
	async function follow(): Promise<void> {
		stopped = false
		clearTimeout(timer)
		await refresh()
		if (stopped || isReady.value) return
		const wait = state.value?.stage === 'failed' ? SLOW_POLL_MS : POLL_MS
		timer = setTimeout(follow, wait)
	}

	function stop(): void {
		stopped = true
		clearTimeout(timer)
	}

	async function retrySetup(): Promise<void> {
		await postFrappe(methodUrl(API.completeSiteSetup), { team: team.value })
		await follow()
	}

	async function invite(rows: InviteRow[]): Promise<InviteResponse> {
		const answer = await postFrappe<InviteResponse>(
			methodUrl(API.inviteSiteMembers),
			{ team: team.value, rows },
		)
		if (state.value) state.value.seats = answer.seats
		return answer
	}

	async function applyMasterSetup(
		config: MasterSetupConfig,
	): Promise<MasterSetupReport> {
		return postFrappe<MasterSetupReport>(methodUrl(API.applyMasterSetup), {
			team: team.value,
			config,
		})
	}

	/** Sign the owner in to the workspace as themselves, through the console's site login. */
	async function openWorkspace(site: string): Promise<void> {
		for (let attempt = 1; attempt <= LOGIN_ATTEMPTS; attempt++) {
			const login = await postFrappe<SiteLogin>(methodUrl(API.loginSite), {
				name: site,
			})
			if (login.login_url) {
				window.location.assign(login.login_url)
				return
			}
			await new Promise((resolve) => setTimeout(resolve, LOGIN_RETRY_MS))
		}
		throw new Error('Your workspace did not answer. Try again in a minute.')
	}

	onBeforeUnmount(stop)

	return {
		state,
		stateError,
		isReady,
		follow,
		refresh,
		stop,
		retrySetup,
		invite,
		applyMasterSetup,
		openWorkspace,
	}
}
