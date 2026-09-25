import { ButtonLink } from "@/components/Button";
import { Icon } from "@/components/Icon";
import { PageHeader } from "@/components/PageHeader";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";

export function NotFoundPage() {
  useDocumentTitle("Page not found");
  return (
    <PageHeader
      eyebrow="404"
      title="This page does not exist"
      description="The address may be mistyped, or the page may belong to a later phase of RUMIN."
      actions={
        <ButtonLink to="/dashboard" variant="primary" iconAfter={<Icon name="arrowRight" />}>
          Go to the overview
        </ButtonLink>
      }
    />
  );
}
