import {useEffect} from 'react';
import {ProjectPage} from './pages/ProjectPage';
import {ProjectDashboard} from './pages/ProjectDashboard';
import {useProjectStore} from './stores/projectStore';
import {useProjectRecovery} from './hooks/useProjectRecovery';

export default function MainApp(){
  const projectId=useProjectStore(state=>state.projectId);
  const initialize=useProjectStore(state=>state.initializeProjects);
  useEffect(()=>{void initialize();},[initialize]);
  useProjectRecovery();
  return projectId?<ProjectPage/>:<ProjectDashboard/>;
}
