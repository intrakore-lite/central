import frappe
from frappe.utils import escape_html, get_url

# The defaults when Central Settings leaves the brand fields empty.
BRAND_NAME = "Intrakore Cloud"
BRAND_LOGO = "/assets/central/images/intrakore-logo.png"


def get_brand_name() -> str:
	"""The platform's name as customers see it in the console, emails and messages."""
	return frappe.get_cached_doc("Central Settings").brand_name or BRAND_NAME


def get_brand() -> dict[str, str | None]:
	"""The console boot's brand: the name, the uploaded logo or None for the bundled one, and
	the policies page or None to hide the terms notice."""
	settings = frappe.get_cached_doc("Central Settings")
	return {
		"title": settings.brand_name or BRAND_NAME,
		"logo_url": settings.brand_logo or None,
		"policies_url": settings.policies_url or None,
	}


def get_email_brand() -> dict[str, str]:
	"""The platform's email header: the name and an absolute logo URL. Escaped, because an
	operator writes them and Jinja does not escape. A product's own branding replaces it."""
	brand = get_brand()
	logo_url = get_url(brand["logo_url"] or BRAND_LOGO)
	return {"title": escape_html(brand["title"]), "logo_url": escape_html(logo_url)}
