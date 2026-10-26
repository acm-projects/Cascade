import { useState } from "react";
import TopNav from "../components/TopNav";
import Button from "../components/ui/Button";
import Modal from "../components/ui/Modal";
import Spinner from "../components/ui/Spinner";
import EmptyState from "../components/ui/EmptyState";
import { useToast } from "../components/ui/ToastContext";
import "./UiPreviewPage.css";

// /dev/ui (only while running `npm run dev`): every shared component on one page,
// so reviewers and teammates can see them without clicking through the app.
function UiPreviewPage() {
  const [modalOpen, setModalOpen] = useState(false);
  const toast = useToast();

  return (
    <div className="ui-preview leaf-page">
      {/* The same TopNav twice, so you can see both looks without picking clips */}
      <p className="ui-preview-label">TopNav, clips picked: every step unlocked (on the Editor page)</p>
      <TopNav projectTitle="Demo project" projectId="demo" active="editor" canOpenEditor canOpenExport />
      <p className="ui-preview-label">TopNav, no clips picked yet: Editor and Export locked (on the AI Studio page)</p>
      <TopNav projectTitle="Demo project" projectId="demo" active="studio" />

      <main className="ui-preview-body">
        <h1 className="ui-preview-heading">UI kit</h1>

        <section className="ui-preview-card wood-panel">
          <h2>Button</h2>
          {["primary", "secondary", "ghost"].map((variant) => (
            <div key={variant} className="ui-preview-row">
              <code>{variant}</code>
              <Button variant={variant}>Medium</Button>
              <Button variant={variant} size="sm">Small</Button>
              <Button variant={variant} disabled>Disabled</Button>
            </div>
          ))}
        </section>

        <section className="ui-preview-card wood-panel">
          <h2>Modal</h2>
          <Button variant="primary" onClick={() => setModalOpen(true)}>Open modal</Button>
          <p className="ui-preview-hint">Close it with Esc, a click outside, or ✕.</p>
        </section>

        <section className="ui-preview-card wood-panel">
          <h2>Toast</h2>
          <div className="ui-preview-row">
            <Button onClick={() => toast.show("Saved!")}>Success toast</Button>
            <Button onClick={() => toast.show("Upload failed", "error")}>Error toast</Button>
          </div>
        </section>

        <section className="ui-preview-card wood-panel">
          <h2>Spinner</h2>
          <div className="ui-preview-row">
            <Spinner size={16} />
            <Spinner />
            <Spinner size={56} />
          </div>
        </section>

        <section className="ui-preview-card wood-panel">
          <h2>EmptyState</h2>
          <EmptyState
            icon="🎬"
            title="No projects yet"
            text="Upload a video and Cascade will find the best clips."
            action={{ label: "+ New Project", onClick: () => toast.show("New project clicked") }}
          />
        </section>
      </main>

      {modalOpen && (
        <Modal title="Delete this project?" onClose={() => setModalOpen(false)}>
          <p>This can't be undone. (It's only a demo, nothing gets deleted.)</p>
          <div className="ui-preview-row ui-preview-actions">
            <Button variant="ghost" size="sm" onClick={() => setModalOpen(false)}>Cancel</Button>
            <Button variant="primary" size="sm" onClick={() => setModalOpen(false)}>Delete</Button>
          </div>
        </Modal>
      )}
    </div>
  );
}

export default UiPreviewPage;
