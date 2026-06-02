import { WorkbenchAppView } from './components/workbench/WorkbenchAppView';
import { useWorkbenchController } from './hooks/useWorkbenchController';

function App() {
  const controller = useWorkbenchController();
  return <WorkbenchAppView controller={controller} />;
}

export default App;
