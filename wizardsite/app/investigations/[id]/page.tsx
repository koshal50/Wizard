import ArchitectureViewer from "@/components/architecture-viewer"

export const metadata = { title: "Architecture investigation | Wizard" }
export default function InvestigationPage({ params }: { params: { id: string } }) {
  return <ArchitectureViewer id={params.id} />
}
