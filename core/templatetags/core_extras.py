"""Custom template filters for the core app."""
from django import template

register = template.Library()

# Map step slugs to emoji icons for the services list preview
STEP_ICONS = {
    'paid': '💰',
    'docs_received': '📄',
    'application_prepared': '📝',
    'submitted': '📤',
    'done': '✅',
    'p45_verified': '📋',
    'docs_collected': '📁',
    'submitted_hmrc': '📨',
    'refund_processed': '💳',
    'info_gathered': '📋',
    'return_prepared': '📑',
    'filed': '📂',
    'onboarded': '👤',
    'books_updated': '📒',
}


@register.filter
def step_icon(slug):
    """Return an emoji icon for a service step slug, or a default bullet."""
    return STEP_ICONS.get((slug or '').lower(), '•')
