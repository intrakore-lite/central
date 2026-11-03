import frappe
from frappe.rate_limiter import rate_limit
from frappe.utils.translations import _lt

from central.utils.guards import require_capability


@frappe.whitelist(methods=["GET"])
@require_capability(
	"billing:manage", _lt("Only a team admin can set up this team. Ask the team owner to continue.")
)
def get_onboarding(team: str | None = None, product: str | None = None) -> dict:
	"""The product, saved answers, seat prices and trust content of the onboarding pages."""
	from central.signups.onboarding import get_onboarding as read

	return read(team, product)


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=30, seconds=60 * 60, user_based=True)
@require_capability(
	"billing:manage", _lt("Only a team admin can set up this team. Ask the team owner to continue.")
)
def save_profile(
	full_name: str,
	mobile: str,
	country: str,
	organisation: str,
	business_type: str,
	headcount_bracket: str,
	seats: int,
	turnover_band: str | None = None,
	team: str | None = None,
) -> dict:
	"""Store onboarding step 1 on the Team and its Billing Profile. Team.validate also
	requires team:edit for the new team name."""
	from central.signups.onboarding import save_profile as save

	return save(
		team,
		{
			"full_name": full_name,
			"mobile": mobile,
			"country": country,
			"organisation": organisation,
			"business_type": business_type,
			"headcount_bracket": headcount_bracket,
			"turnover_band": turnover_band,
			"seats": seats,
		},
	)


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=10, seconds=60 * 60, user_based=True)
@require_capability(
	"server:create", _lt("You can't create sites for this Team. Ask a team admin to review your access.")
)
def start_site(team: str | None = None, product: str | None = None) -> dict:
	"""Queue the team's site after its card is saved. See `central.signups.onboarding.start_site`."""
	from central.signups.onboarding import start_site as start

	return start(team, product)
