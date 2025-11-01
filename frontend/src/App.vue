<script setup>
import { ref, watch, computed, nextTick } from 'vue';
import axios from 'axios';

const topic = ref('');
const clusteredData = ref(null);
const graphData = ref(null);
const loading = ref(false);
const error = ref(null);

// Computed property to generate Mermaid graph definition
const mermaidChart = computed(() => {
  if (!graphData.value || !graphData.value.nodes || !graphData.value.edges) {
    return '';
  }

  let chart = 'graph TD\n';

  // Add nodes
  for (const nodeId in graphData.value.nodes) {
    const node = graphData.value.nodes[nodeId];
    let label = node.attributes.label || nodeId;
    if (node.attributes.keywords && node.attributes.keywords.length > 0) {
      label += '\nKeywords: ' + node.attributes.keywords.join(', ');
    }
    chart += `    ${nodeId}["${label}"]\n`;
  }

  // Add edges
  for (const edge of graphData.value.edges) {
    chart += `    ${edge.source} -- "${edge.relationship} (Weight: ${edge.weight})" --> ${edge.target}\n`;
  }

  return chart;
});

// Watch for changes in graphData and re-render Mermaid chart
watch(graphData, async (newGraphData) => {
  if (newGraphData) {
    await nextTick(); // Wait for DOM to update
    if (document.getElementById('mermaid-graph')) {
      // Clear previous graph
      document.getElementById('mermaid-graph').innerHTML = '';
      // Render new graph
      mermaid.render('graphDiv', mermaidChart.value).then(({ svg, bindFunctions }) => {
        document.getElementById('mermaid-graph').innerHTML = svg;
        bindFunctions();
      });
    }
  }
});

async function processTopic() {
  loading.value = true;
  error.value = null;
  clusteredData.value = null;
  graphData.value = null;
  try {
    const response = await axios.post(`http://localhost:8000/process-topic/${topic.value}`);
    clusteredData.value = response.data.clustered_data;
    graphData.value = response.data.graph;
  } catch (err) {
    error.value = 'Failed to fetch data: ' + err.message;
    console.error(err);
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div id="app" class="container mx-auto p-4">
    <h1 class="text-3xl font-bold mb-4">Social Trend Analyser</h1>

    <div class="mb-4">
      <input
        type="text"
        v-model="topic"
        placeholder="Enter topic (e.g., python)"
        class="border p-2 rounded w-full md:w-1/2 lg:w-1/3"
      />
      <button
        @click="processTopic"
        :disabled="loading"
        class="bg-blue-500 text-white px-4 py-2 rounded ml-2 hover:bg-blue-600 disabled:opacity-50"
      >
        {{ loading ? 'Processing...' : 'Analyze' }}
      </button>
    </div>

    <div v-if="error" class="text-red-500 mb-4">{{ error }}</div>

    <div v-if="clusteredData" class="mb-4">
      <h2 class="text-2xl font-semibold mb-2">Clustered Data:</h2>
      <div v-for="item in clusteredData" :key="item.text" class="bg-gray-100 p-2 rounded mb-2">
        <p><strong>Cluster {{ item.cluster }}</strong>: {{ item.text.substring(0, 150) }}...</p>
      </div>
    </div>

    <div v-if="graphData" class="mb-4">
      <h2 class="text-2xl font-semibold mb-2">Graph Visualization:</h2>
      <div id="mermaid-graph" class="mermaid bg-gray-100 p-4 rounded"></div>
    </div>
  </div>
</template>

<style>
/* Basic Tailwind-like styles for demonstration */
.container {
  max-width: 960px;
}
.text-3xl {
  font-size: 1.875rem; /* 30px */
  line-height: 2.25rem; /* 36px */
}
.font-bold {
  font-weight: 700;
}
.mb-4 {
  margin-bottom: 1rem;
}
.text-2xl {
  font-size: 1.5rem; /* 24px */
  line-height: 2rem; /* 32px */
}
.font-semibold {
  font-weight: 600;
}
.mb-2 {
  margin-bottom: 0.5rem;
}
.border {
  border-width: 1px;
  border-color: #e2e8f0;
}
.p-2 {
  padding: 0.5rem;
}
.rounded {
  border-radius: 0.25rem;
}
.w-full {
  width: 100%;
}
.md\:w-1\/2 {
  width: 50%;
}
.lg\:w-1\/3 {
  width: 33.333333%;
}
.bg-blue-500 {
  background-color: #3b82f6;
}
.text-white {
  color: #fff;
}
.px-4 {
  padding-left: 1rem;
  padding-right: 1rem;
}
.py-2 {
  padding-top: 0.5rem;
  padding-bottom: 0.5rem;
}
.ml-2 {
  margin-left: 0.5rem;
}
.hover\:bg-blue-600:hover {
  background-color: #2563eb;
}
.disabled\:opacity-50:disabled {
  opacity: 0.5;
}
.text-red-500 {
  color: #ef4444;
}
.bg-gray-100 {
  background-color: #f7fafc;
}
.bg-gray-800 {
  background-color: #2d3748;
}
.overflow-auto {
  overflow: auto;
}
.mt-2 {
  margin-top: 0.5rem;
}
</style>
