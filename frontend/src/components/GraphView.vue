<template>
  <div class="graph-view-container" ref="containerRef">
    <div v-if="!hasGraphData" class="graph-empty-state">
      <p>Send a message about a social area you'd like to learn about to visualize the graph.</p>
    </div>
    <div v-show="hasGraphData" class="graph-visualization" ref="networkRef"></div>
    <transition name="graph-whiteout-fade">
      <div v-if="hideGraph" class="graph-whiteout-overlay" :style="{ background: overlayColor }"></div>
    </transition>
    <div v-if="currentAnnotationText" class="annotation-tooltip" :style="annotationTooltipStyle">
      <div class="annotation-content">{{ currentAnnotationText }}</div>
      <div v-if="selectedNodeAnnotations.length > 1" class="annotation-nav">
        <button 
          class="nav-arrow nav-arrow-left" 
          @click="previousAnnotation"
          :disabled="currentAnnotationIndex === 0"
        >
          <i class="fa fa-chevron-left"></i>
        </button>
        <div class="annotation-counter">
          {{ currentAnnotationIndex + 1 }} / {{ selectedNodeAnnotations.length }}
        </div>
        <button 
          class="nav-arrow nav-arrow-right" 
          @click="nextAnnotation"
          :disabled="currentAnnotationIndex === selectedNodeAnnotations.length - 1"
        >
          <i class="fa fa-chevron-right"></i>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, computed, nextTick } from 'vue';
import { Network } from 'vis-network';
import { DataSet } from 'vis-data';

interface Node {
  summary: string;
  embedding: number[];
  ideas: Array<{idea: string; embedding: number[]}>;
}

interface GraphData {
  nodes: Node[];
  annotations: Record<string, string>;
  similarity_matrix: number[][];
}

interface AnnotationInfo {
  key: string;
  text: string;
  nodeIndices: number[];
}

const props = defineProps<{
  graphData: GraphData | null;
  chatOpen: boolean;
  hideGraph?: boolean;
  overlayColor?: string;
}>();

const containerRef = ref<HTMLElement | null>(null);
const networkRef = ref<HTMLElement | null>(null);
let network: Network | null = null;
let edgesDataSet: DataSet | null = null;
let annotationToEdgesMap = new Map<string, string[]>(); // annotation key -> edge IDs
let edgeIdMap = new Map<string, string>(); // edge key (from-to) -> edge ID

// State for annotation navigation
const selectedNodeId = ref<number | null>(null);
const selectedNodeAnnotations = ref<AnnotationInfo[]>([]);
const currentAnnotationIndex = ref(0);
const selectedNodePosition = ref({ x: 0, y: 0 });

const hasGraphData = computed(() => props.graphData !== null);
const currentAnnotation = computed(() => selectedNodeAnnotations.value[currentAnnotationIndex.value] || null);
const currentAnnotationText = computed(() => currentAnnotation.value?.text || null);
const currentAnnotationKey = computed(() => currentAnnotation.value?.key || null);

// Position annotation tooltip near selected node, ensuring it stays on screen
const annotationTooltipStyle = computed(() => {
  const padding = 20;
  const tooltipWidth = 300;
  const tooltipHeight = selectedNodeAnnotations.value.length > 1 ? 200 : 150; // Slightly taller if nav buttons present
  
  let left = selectedNodePosition.value.x + 60;
  let top = selectedNodePosition.value.y - 10;
  
  // Check if tooltip would go off right edge
  if (left + tooltipWidth > window.innerWidth - padding) {
    left = selectedNodePosition.value.x - tooltipWidth - 20; // Put it to the left instead
  }
  
  // Check if tooltip would go off left edge
  if (left < padding) {
    left = padding;
  }
  
  // Check if tooltip would go off bottom edge
  if (top + tooltipHeight > window.innerHeight - padding) {
    top = window.innerHeight - tooltipHeight - padding;
  }
  
  // Check if tooltip would go off top edge
  if (top < padding) {
    top = padding;
  }
  
  return {
    top: `${top}px`,
    left: `${left}px`,
  };
});


function previousAnnotation() {
  if (currentAnnotationIndex.value > 0) {
    currentAnnotationIndex.value--;
    updateEdgeHighlighting();
  }
}

function nextAnnotation() {
  if (currentAnnotationIndex.value < selectedNodeAnnotations.value.length - 1) {
    currentAnnotationIndex.value++;
    updateEdgeHighlighting();
  }
}

function updateEdgeHighlighting() {
  if (!edgesDataSet || !network || !currentAnnotationKey.value) {
    // Reset all edges and nodes if no annotation selected
    resetAllToNormal();
    return;
  }

  const currentAnnotation = selectedNodeAnnotations.value[currentAnnotationIndex.value];
  if (!currentAnnotation) return;

  const currentEdges = annotationToEdgesMap.get(currentAnnotationKey.value) || [];
  const involvedNodeIds = new Set(currentAnnotation.nodeIndices);
  
  // Update edges: highlight involved ones, grey out others
  const allEdges = edgesDataSet.get();
  allEdges.forEach((edge: any) => {
    if (!edge.originalWidth) {
      edge.originalWidth = edge.width;
      edge.originalColor = { ...edge.color };
    }
    
    const isInvolved = currentEdges.includes(edge.id);
    
    edgesDataSet.update({
      id: edge.id,
      width: isInvolved ? (edge.originalWidth || 2) + 3 : 1,
      color: isInvolved ? {
        color: 'rgba(10, 186, 181, 1)',
        highlight: 'rgba(10, 186, 181, 1)',
      } : {
        color: 'rgba(150, 150, 150, 0.2)',
        highlight: 'rgba(150, 150, 150, 0.3)',
      },
    });
  });

  // Update nodes: highlight involved ones, grey out others
  const nodes = (network as any).body?.data?.nodes;
  if (nodes) {
    const allNodes = nodes.get();
    allNodes.forEach((node: any) => {
      if (!node.originalColor) {
        node.originalColor = { ...node.color };
      }
      
      const isInvolved = involvedNodeIds.has(node.id);
      
      nodes.update({
        id: node.id,
        color: isInvolved ? node.originalColor : {
          background: '#e0e0e0',
          border: '#b0b0b0',
          highlight: {
            background: '#d0d0d0',
            border: '#909090',
          },
        },
      });
    });
  }
}

function resetAllToNormal() {
  if (!edgesDataSet) return;
  
  // Reset all edges
  const allEdges = edgesDataSet.get();
  allEdges.forEach((edge: any) => {
    if (edge.originalWidth && edge.originalColor) {
      edgesDataSet.update({
        id: edge.id,
        width: edge.originalWidth,
        color: edge.originalColor,
      });
    }
  });

  // Reset all nodes
  const nodes = network ? (network as any).body?.data?.nodes : null;
  if (nodes) {
    const allNodes = nodes.get();
    allNodes.forEach((node: any) => {
      if (node.originalColor) {
        nodes.update({
          id: node.id,
          color: node.originalColor,
        });
      }
    });
  }
}

async function buildGraph() {
  if (!props.graphData) {
    return;
  }
  
  if (!networkRef.value) {
    await nextTick();
    await new Promise(resolve => setTimeout(resolve, 100));
    if (!networkRef.value) {
      return;
    }
  }

  const { nodes: rawNodes, annotations, similarity_matrix } = props.graphData;
  
  if (!Array.isArray(rawNodes) || !annotations || !Array.isArray(similarity_matrix)) {
    return;
  }

  // Reset state
  selectedNodeId.value = null;
  selectedNodeAnnotations.value = [];
  currentAnnotationIndex.value = 0;
  annotationToEdgesMap.clear();
  edgeIdMap.clear();
  resetAllToNormal();

  // Calculate num_ideas from ideas array length
  const nodesWithIdeasCount = rawNodes.map((node, index) => ({
    ...node,
    id: index, // Use index as id since nodes array doesn't have explicit id
    num_ideas: node.ideas ? node.ideas.length : 1,
  }));
  
  const maxIdeas = Math.max(...nodesWithIdeasCount.map(n => n.num_ideas));
  const minSize = 20;
  const maxSize = 60;

  const nodes = new DataSet(
    nodesWithIdeasCount.map((node, index) => ({
      id: index,
      label: node.summary || `Node ${index}`,
      value: node.num_ideas,
      size: minSize + (node.num_ideas / maxIdeas) * (maxSize - minSize),
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

  const edges: any[] = [];
  const edgeMap = new Map<string, any>();

  // Build edges and track which annotation each edge belongs to
  Object.keys(annotations).forEach(annotationKey => {
    let nodeIndices: number[] = [];
    
    if (Array.isArray(annotationKey) || (typeof annotationKey === 'string' && annotationKey.startsWith('['))) {
      const parts = typeof annotationKey === 'string' ? JSON.parse(annotationKey) : annotationKey;
      if (Array.isArray(parts) && parts.length >= 2) {
        nodeIndices = parts.map(Number);
      } else {
        return;
      }
    } else {
      const parts = annotationKey.split('-').map(Number);
      if (parts.length >= 2) {
        nodeIndices = parts;
      } else {
        return;
      }
    }
    
    const annotationText = annotations[annotationKey];
    const edgeIds: string[] = [];

    // Create edges between all pairs of nodes in this annotation group
    for (let i = 0; i < nodeIndices.length; i++) {
      for (let j = i + 1; j < nodeIndices.length; j++) {
        const from = nodeIndices[i];
        const to = nodeIndices[j];
        const similarity = similarity_matrix[from]?.[to] || 0;
        
        if (similarity > 0) {
          const opacity = Math.min(similarity, 1);
          const width = 2 + (similarity * 4);
          const edgeKey = `${Math.min(from, to)}-${Math.max(from, to)}`;
          
          if (!edgeMap.has(edgeKey)) {
            const edgeId = `edge-${from}-${to}`;
            const originalColor = {
              color: `rgba(10, 186, 181, ${opacity})`,
              highlight: 'rgba(10, 186, 181, 1)',
            };
            edges.push({
              id: edgeId,
              from,
              to,
              value: similarity,
              width,
              originalWidth: width,
              originalColor: originalColor,
              color: originalColor,
            });
            edgeMap.set(edgeKey, true);
            edgeIdMap.set(edgeKey, edgeId);
            edgeIds.push(edgeId);
          } else {
            // Edge already exists, add to this annotation's edge list
            const existingEdgeId = edgeIdMap.get(edgeKey);
            if (existingEdgeId && !edgeIds.includes(existingEdgeId)) {
              edgeIds.push(existingEdgeId);
            }
          }
        }
      }
    }

    // Store which edges belong to this annotation
    if (edgeIds.length > 0) {
      annotationToEdgesMap.set(annotationKey, edgeIds);
    }
  });

  edgesDataSet = new DataSet(edges);

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
        template: '',
      },
    },
  };

  if (network) {
    network.destroy();
  }

  network = new Network(networkRef.value, data, options);

  // Handle node click
  network.on('click', (params: any) => {
    if (params.nodes && params.nodes.length > 0) {
      const clickedNodeId = params.nodes[0];
      const nodePos = network!.getPositions([clickedNodeId])[clickedNodeId];
      const canvas = networkRef.value!.querySelector('canvas');
      
      if (canvas && nodePos) {
        const rect = canvas.getBoundingClientRect();
        selectedNodePosition.value = {
          x: nodePos.x + rect.left,
          y: nodePos.y + rect.top,
        };
      } else {
        // Fallback: use center of viewport if position not available
        selectedNodePosition.value = {
          x: window.innerWidth / 2,
          y: window.innerHeight / 2,
        };
      }

      // Find all annotations that contain this node
      const nodeAnnotations: AnnotationInfo[] = [];
      Object.keys(props.graphData!.annotations).forEach(annotationKey => {
        let nodeIndices: number[] = [];
        
        if (typeof annotationKey === 'string' && annotationKey.startsWith('[')) {
          nodeIndices = JSON.parse(annotationKey).map(Number);
        } else if (typeof annotationKey === 'string' && annotationKey.includes('-')) {
          nodeIndices = annotationKey.split('-').map(Number);
        }
        
        if (nodeIndices.includes(clickedNodeId)) {
          nodeAnnotations.push({
            key: annotationKey,
            text: props.graphData!.annotations[annotationKey],
            nodeIndices,
          });
        }
      });

      selectedNodeId.value = clickedNodeId;
      selectedNodeAnnotations.value = nodeAnnotations;
      currentAnnotationIndex.value = 0;
      
      if (nodeAnnotations.length > 0) {
        updateEdgeHighlighting();
      }
    } else {
      // Clicked on empty space - deselect
      selectedNodeId.value = null;
      selectedNodeAnnotations.value = [];
      currentAnnotationIndex.value = 0;
      resetAllToNormal();
    }
  });

  const handleResize = () => {
    if (network && networkRef.value) {
      network.setSize(networkRef.value.clientWidth, networkRef.value.clientHeight);
    }
  };

  window.addEventListener('resize', handleResize);
  
  (network as any).__cleanup = () => {
    window.removeEventListener('resize', handleResize);
  };
}

watch(() => props.graphData, async (newData) => {
  if (!newData) return;
  await nextTick();
  buildGraph();
}, { deep: true });

onMounted(async () => {
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


.nav-arrow {
  background: #0ABAB5;
  color: #fff;
  border: none;
  border-radius: 50%;
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background 0.2s;
}

.nav-arrow:hover:not(:disabled) {
  background: #089895;
}

.nav-arrow:disabled {
  background: #B0F0ED;
  cursor: not-allowed;
  opacity: 0.5;
}

.annotation-counter {
  font-size: 0.9rem;
  color: #0ABAB5;
  font-weight: 600;
  min-width: 40px;
  text-align: center;
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
  pointer-events: auto;
  word-wrap: break-word;
  display: flex;
  flex-direction: column;
}

.annotation-content {
  color: #222;
  font-size: 0.95rem;
  line-height: 1.5;
  white-space: pre-line;
  margin-bottom: 8px;
}

.annotation-nav {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid #0ABAB5;
}

.graph-whiteout-overlay {
  background: #faf9f6;
  height: 100%;
  left: 0;
  opacity: 1;
  pointer-events: none;
  position: absolute;
  top: 0;
  width: 100%;
  z-index: 20;
}

.graph-whiteout-fade-enter-active,
.graph-whiteout-fade-leave-active {
  transition: opacity 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}

.graph-whiteout-fade-enter-from,
.graph-whiteout-fade-leave-to {
  opacity: 0;
}

.graph-whiteout-fade-enter-to,
.graph-whiteout-fade-leave-from {
  opacity: 1;
}
</style>
