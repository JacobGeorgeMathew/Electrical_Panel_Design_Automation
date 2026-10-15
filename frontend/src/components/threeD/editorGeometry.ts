import { EditorTransform } from '../../stores/projectStore';
import { PhysicalComponent } from '../../types/pdm';

export type EditorWarning = {
  id: string;
  type: 'COLLISION' | 'CLEARANCE' | 'BOUNDARY';
  componentIds: string[];
  message: string;
};

export function componentTransform(
  component: PhysicalComponent,
  draft?: EditorTransform,
): EditorTransform {
  return draft || {
    x: component.position.x,
    y: component.position.y,
    z: component.position.z,
    rotation_deg: component.rotation_deg || 0,
  };
}

function footprint(component: PhysicalComponent, transform: EditorTransform) {
  const radians = (transform.rotation_deg * Math.PI) / 180;
  const width = Math.abs(component.width * Math.cos(radians)) + Math.abs(component.height * Math.sin(radians));
  const height = Math.abs(component.width * Math.sin(radians)) + Math.abs(component.height * Math.cos(radians));
  return { x0: transform.x + component.width / 2 - width / 2,
    x1: transform.x + component.width / 2 + width / 2,
    y0: transform.y + component.height / 2 - height / 2,
    y1: transform.y + component.height / 2 + height / 2 };
}

export function analyzeEditorGeometry(
  components: PhysicalComponent[],
  transforms: Record<string, EditorTransform>,
  enclosure: { width: number; height: number; depth: number },
): EditorWarning[] {
  const warnings: EditorWarning[] = [];
  const boxes = components.map((component) => ({
    component,
    transform: componentTransform(component, transforms[component.cem_component_id]),
    bounds: footprint(component, componentTransform(component, transforms[component.cem_component_id])),
  }));

  for (const { component, transform, bounds } of boxes) {
    if (bounds.x0 < 0 || bounds.y0 < 0 || bounds.x1 > enclosure.width || bounds.y1 > enclosure.height
      || transform.z < 0 || transform.z + component.depth > enclosure.depth) {
      warnings.push({ id: `boundary:${component.cem_component_id}`, type: 'BOUNDARY',
        componentIds: [component.cem_component_id],
        message: `${component.cem_component_id} extends beyond the selected enclosure bounds.` });
    }
  }

  for (let i = 0; i < boxes.length; i += 1) {
    for (let j = i + 1; j < boxes.length; j += 1) {
      const a = boxes[i];
      const b = boxes[j];
      const gapX = Math.max(0, a.bounds.x0 - b.bounds.x1, b.bounds.x0 - a.bounds.x1);
      const gapY = Math.max(0, a.bounds.y0 - b.bounds.y1, b.bounds.y0 - a.bounds.y1);
      const clearance = Math.hypot(gapX, gapY);
      if (gapX === 0 && gapY === 0) {
        warnings.push({ id: `collision:${a.component.cem_component_id}:${b.component.cem_component_id}`,
          type: 'COLLISION', componentIds: [a.component.cem_component_id, b.component.cem_component_id],
          message: `${a.component.cem_component_id} overlaps ${b.component.cem_component_id}.` });
        continue;
      }

      let required = 20;
      if (a.component.rail_id && b.component.rail_id) {
        required = a.component.rail_id === b.component.rail_id ? 4 : 0;
      }
      if (required > 0 && clearance < required) {
        warnings.push({ id: `clearance:${a.component.cem_component_id}:${b.component.cem_component_id}`,
          type: 'CLEARANCE', componentIds: [a.component.cem_component_id, b.component.cem_component_id],
          message: `${a.component.cem_component_id} is ${clearance.toFixed(1)} mm from ${b.component.cem_component_id}; prototype minimum is ${required} mm.` });
      }
    }
  }
  return warnings;
}
