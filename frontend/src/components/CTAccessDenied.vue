<template>
  <div class="fixed inset-0 flex flex-col items-center justify-center bg-background z-50">
    <div class="flex flex-col items-center max-w-md text-center">
      <span class="material-symbols-outlined text-6xl text-destructive mb-4" data-icon="lock">lock</span>
      <h2 class="text-2xl font-bold text-foreground mb-2">Truy cập bị từ chối</h2>
      <p class="text-muted-foreground mb-6">
        Bạn không có quyền truy cập vào ứng dụng này, hoặc ứng dụng chưa được công bố (Published) bởi Quản trị viên.
      </p>
      <button @click="goHome" class="shadcn-btn shadcn-btn-primary px-6 py-2">
        Quay về trang chủ
      </button>
    </div>
  </div>
</template>

<script setup>
const goHome = () => {
  window.location.href = '/'
}
</script>
