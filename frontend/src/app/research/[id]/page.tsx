import { RunPage } from "@/modules/research/components/RunPage";

export default async function ResearchRunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <RunPage id={id} />;
}
