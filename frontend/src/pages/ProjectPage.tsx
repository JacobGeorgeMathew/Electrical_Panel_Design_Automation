import React, { useEffect } from 'react';
import { useProjectStore } from '../stores/projectStore';
import { Header } from '../components/common/Header';
import { Questionnaire } from '../components/requirements/Questionnaire';
import { SchematicViewer } from '../components/schematic/SchematicViewer';
import { Layout2DViewer } from '../components/layout/Layout2DViewer';
import { Panel3DViewer } from '../components/threeD/Panel3DViewer';
import { ValidationPanel } from '../components/validation/ValidationPanel';
import { BOMTable } from '../components/bom/BOMTable';
import { ChangePropagationModal } from '../components/common/ChangePropagationModal';
import { ProjectPersistenceBar } from '../components/projects/ProjectPersistenceBar';
import { CatalogBrowser } from '../components/catalog/CatalogBrowser';

export const ProjectPage: React.FC = () => {
  const { activeTab, initializeProjects } = useProjectStore();

  useEffect(() => {
    initializeProjects();
  }, []);

  return (
    <div className="flex h-dvh min-h-0 flex-col overflow-hidden bg-slate-950 text-slate-100">
      <Header />
      <ProjectPersistenceBar />

      <main className="flex-1 min-h-0 min-w-0 flex flex-col relative overflow-hidden">
        {activeTab === 'requirements' && <Questionnaire />}
        {activeTab === 'schematic' && <SchematicViewer />}
        {activeTab === 'layout2d' && <Layout2DViewer />}
        {activeTab === 'threeD' && <Panel3DViewer />}
        {activeTab === 'validation' && <ValidationPanel />}
        {activeTab === 'bom' && (
          <section
            aria-label="Bill of materials"
            tabIndex={0}
            className="flex-1 min-h-0 min-w-0 overflow-y-auto"
          >
            <BOMTable />
          </section>
        )}
        {activeTab === 'catalog' && <CatalogBrowser />}
      </main>

      <ChangePropagationModal />
    </div>
  );
};
