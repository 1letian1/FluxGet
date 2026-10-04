"""Built-in rules shipped with the application."""

from backend.rules.models import RuleDefinition


JENKINS_HPI_RULE = RuleDefinition(
    id="builtin:jenkins-hpi",
    name="Jenkins HPI",
    base_url="",
    url_template="{base_url}/{name}/{version}/{name}.hpi",
    filename_template="{name}-{version}.hpi",
    default_ext="hpi",
    builtin=True,
)
