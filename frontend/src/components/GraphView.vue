<template>
  <div class="graph-view-container" ref="containerRef">
    <div v-if="!hasGraphData" class="graph-empty-state">
      <p>Send a message about a social area you'd like to learn about to visualize the graph.</p>
    </div>
    <div v-show="hasGraphData" class="graph-visualization" ref="networkRef"></div>
    <div v-if="selectedAnnotation" class="annotation-tooltip" :style="tooltipStyle">
      <div class="annotation-content">{{ selectedAnnotation }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, computed, nextTick } from 'vue';
import { Network } from 'vis-network';
import { DataSet } from 'vis-data';

interface Node {
  id: number;
  label: string;
  num_ideas?: number;
  summary?: string;
}

interface GraphData {
  nodes: Node[];
  annotations: Record<string, string>;
  similarity_matrix: number[][];
}

const props = defineProps<{
  graphData: GraphData | null;
  chatOpen: boolean;
}>();

const containerRef = ref<HTMLElement | null>(null);
const networkRef = ref<HTMLElement | null>(null);
let network: Network | null = null;
const selectedAnnotation = ref<string | null>(null);
const tooltipStyle = ref({ top: '0px', left: '0px' });
const mousePosition = ref({ x: 0, y: 0 });

const hasGraphData = computed(() => props.graphData !== null);

async function buildGraph() {
  if (!props.graphData) {
    console.log('GraphView: No graph data');
    return;
  }
  
  // Ensure networkRef is available
  if (!networkRef.value) {
    console.log('GraphView: networkRef not ready, waiting...');
    await nextTick();
    await new Promise(resolve => setTimeout(resolve, 100));
    if (!networkRef.value) {
      console.error('GraphView: networkRef still not available after waiting');
      return;
    }
  }

  const { nodes: rawNodes, annotations, similarity_matrix } = props.graphData;
  
  // Validate data
  if (!Array.isArray(rawNodes) || !annotations || !Array.isArray(similarity_matrix)) {
    console.error('Invalid graph data format', { 
      nodesIsArray: Array.isArray(rawNodes),
      hasAnnotations: !!annotations,
      matrixIsArray: Array.isArray(similarity_matrix)
    });
    return;
  }

  console.log('Building graph with:', { 
    nodeCount: rawNodes.length, 
    annotationCount: Object.keys(annotations).length 
  });

  // Calculate max ideas for sizing
  const maxIdeas = Math.max(...rawNodes.map(n => n.num_ideas || 1));
  const minSize = 20;
  const maxSize = 60;

  // Build nodes with size proportional to ideas
  const nodes = new DataSet(
    rawNodes.map(node => ({
      id: node.id,
      label: node.label || node.summary || `Node ${node.id}`,
      value: node.num_ideas || 1,
      size: minSize + ((node.num_ideas || 1) / maxIdeas) * (maxSize - minSize),
      font: {
        size: 14,
        face: 'Inter',
      },
      color: {
        background: '#fff',
        border: '#0ABAB5',
        highlight: {
          background: '#B0F0ED',
          border: '#0ABAB5',
        },
      },
      borderWidth: 2,
      shape: 'dot',
    }))
  );

  // Build edges from similarity matrix and annotations
  // Annotations can represent groups of nodes (2+), so we create edges between all pairs in each group
  const edges: any[] = [];
  const edgeMap = new Map<string, any>();

  // Only add edges that are in annotations and have similarity > 0
  Object.keys(annotations).forEach(key => {
    let nodeIndices: number[] = [];
    
    // Handle both string keys like "[0, 1, 2]" and "0-1" format (from Python tuple serialization)
    if (Array.isArray(key) || (typeof key === 'string' && key.startsWith('['))) {
      // Array format like "[0, 1, 2]" - parse the JSON string
      const parts = typeof key === 'string' ? JSON.parse(key) : key;
      if (Array.isArray(parts) && parts.length >= 2) {
        nodeIndices = parts.map(Number);
      } else {
        return;
      }
    } else {
      // String format like "0-1" - legacy format for pairs only
      const parts = key.split('-').map(Number);
      if (parts.length >= 2) {
        nodeIndices = parts;
      } else {
        return;
      }
    }
    
    const annotationText = annotations[key];
    
    // Create edges between all pairs of nodes in this group
    for (let i = 0; i < nodeIndices.length; i++) {
      for (let j = i + 1; j < nodeIndices.length; j++) {
        const from = nodeIndices[i];
        const to = nodeIndices[j];
        const similarity = similarity_matrix[from]?.[to] || 0;
        
        if (similarity > 0) {
          // Calculate opacity and width based on similarity
          const opacity = Math.min(similarity, 1);
          const width = 2 + (similarity * 4);
          
          const edgeKey = `${Math.min(from, to)}-${Math.max(from, to)}`;
          if (!edgeMap.has(edgeKey)) {
          edges.push({
            from,
            to,
            value: similarity,
            width,
            color: {
              color: `rgba(10, 186, 181, ${opacity})`,
              highlight: 'rgba(10, 186, 181, 1)',
            },
            // Store annotation text but don't use title (which triggers default tooltip)
            annotation: annotationText,
          });
            edgeMap.set(edgeKey, true);
          }
        }
      }
    }
  });

  const edgesDataSet = new DataSet(edges);

  const data = {
    nodes,
    edges: edgesDataSet,
  };

  const options = {
    nodes: {
      font: {
        size: 14,
        face: 'Inter',
      },
      scaling: {
        min: minSize,
        max: maxSize,
      },
    },
    edges: {
      smooth: {
        type: 'continuous',
      },
      arrows: {
        to: {
          enabled: false,
        },
      },
    },
    physics: {
      enabled: true,
      stabilization: {
        enabled: true,
        iterations: 200,
      },
      barnesHut: {
        gravitationalConstant: -2000,
        centralGravity: 0.1,
        springLength: 200,
        springConstant: 0.04,
        damping: 0.09,
      },
    },
    interaction: {
      hover: true,
      tooltipDelay: 0,
      zoomView: true,
      dragView: true,
      tooltip: {
        delay: 0,
        template: '', // Disable default tooltip
      },
    },
  };

  // Destroy existing network
  if (network) {
    network.destroy();
  }

  // Create new network
  network = new Network(networkRef.value, data, options);

  // Track mouse position for tooltip
  const handleMouseMove = (event: MouseEvent) => {
    mousePosition.value = { x: event.clientX, y: event.clientY };
  };

  // Handle edge hover for annotations - use tracked mouse position
  network.on('hoverEdge', (params: any) => {
    if (params.edge) {
      const edge = edgesDataSet.get(params.edge);
      if (edge && (edge as any).annotation) {
        selectedAnnotation.value = (edge as any).annotation;
        
        // Use tracked mouse position
        tooltipStyle.value = {
          top: `${mousePosition.value.y - 10}px`, // Position slightly above cursor
          left: `${mousePosition.value.x + 15}px`, // Position to the right of cursor
        };
      }
    }
  });

  // Add mousemove listener to track cursor position
  const canvas = networkRef.value!.querySelector('canvas');
  if (canvas) {
    canvas.addEventListener('mousemove', handleMouseMove);
    (network as any).__mouseMoveHandler = handleMouseMove;
    (network as any).__canvas = canvas;
  }

  network.on('blurEdge', () => {
    selectedAnnotation.value = null;
  });

  // Handle window resize
  const handleResize = () => {
    if (network && networkRef.value) {
      network.setSize(networkRef.value.clientWidth, networkRef.value.clientHeight);
    }
  };

  window.addEventListener('resize', handleResize);
  
  // Store cleanup function
  (network as any).__cleanup = () => {
    window.removeEventListener('resize', handleResize);
    const canvas = (network as any).__canvas;
    const mouseMoveHandler = (network as any).__mouseMoveHandler;
    if (canvas && mouseMoveHandler) {
      canvas.removeEventListener('mousemove', mouseMoveHandler);
    }
  };
}

watch(() => props.graphData, async (newData) => {
  if (!newData) return;
  // Wait for DOM to update so networkRef is available
  await nextTick();
  buildGraph();
}, { deep: true });

onMounted(async () => {
  // Wait for initial DOM render
  await nextTick();
  buildGraph();
});

onUnmounted(() => {
  if (network) {
    const cleanup = (network as any).__cleanup;
    if (cleanup) cleanup();
    network.destroy();
    network = null;
  }
});
</script>

<style scoped>
.graph-view-container {
  height: 100%;
  width: 100%;
  position: relative;
  background: #faf9f6;
}

.graph-empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  width: 100%;
  color: #666;
  font-size: 1.1rem;
  text-align: center;
  padding: 2rem;
}

.graph-visualization {
  height: 100%;
  width: 100%;
}

.annotation-tooltip {
  position: fixed;
  background: #E6F8F7;
  border: 2px solid #0ABAB5;
  border-radius: 12px;
  padding: 12px 16px;
  box-shadow: 0 4px 12px rgba(31, 38, 135, 0.15);
  z-index: 10000;
  max-width: 300px;
  pointer-events: none;
  word-wrap: break-word;
}

.annotation-content {
  color: #222;
  font-size: 0.95rem;
  line-height: 1.5;
}
</style>

