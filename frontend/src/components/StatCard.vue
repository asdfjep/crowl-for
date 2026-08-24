<script setup>
defineProps({
  icon: { type: String, default: 'Star' },
  color: { type: String, default: '#409eff' },
  value: { type: [Number, String], default: 0 },
  label: { type: String, required: true }
})
</script>

<template>
  <div class="stat-card">
    <div class="stat-icon" :style="{ background: color }">
      <el-icon :size="24"><component :is="icon" /></el-icon>
    </div>
    <div>
      <div class="stat-value">{{ value }}</div>
      <div class="stat-label">{{ label }}</div>
    </div>
  </div>
</template>