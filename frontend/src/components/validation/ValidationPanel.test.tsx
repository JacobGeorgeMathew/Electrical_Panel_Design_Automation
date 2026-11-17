import React, {act} from 'react';
import {createRoot} from 'react-dom/client';
import {expect, it} from 'vitest';
import {useProjectStore} from '../../stores/projectStore';
import {ValidationPanel} from './ValidationPanel';

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

it('an empty physical violation list cannot imply complete engineering approval', () => {
  const previous = useProjectStore.getState();
  useProjectStore.setState({pdm: {enclosure_width: 800, enclosure_height: 1200,
    enclosure_depth: 300, validation_results: []} as any});
  const host = document.createElement('div');
  const root = createRoot(host);
  try {
    act(() => root.render(<ValidationPanel/>));
    expect(host.textContent).toContain('Required engineering checks may remain unresolved');
    expect(host.textContent).toContain('does not authorize publication');
    expect(host.textContent).toContain('No violations reported by the implemented physical checks');
    expect(host.textContent).not.toContain('All Design Constraints Passed');
  } finally {
    act(() => root.unmount());
    useProjectStore.setState(previous, true);
  }
});
