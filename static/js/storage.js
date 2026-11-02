/* Lesmarl AI - Made by Mashrur Ahmed Arib - MIT License. See LICENSE. */
window.LesmarlStorage = (() => {
  function isAvailable() {
    try {
      const key = '__lesmarl_storage_test__';
      localStorage.setItem(key, key);
      localStorage.removeItem(key);
      return true;
    } catch (error) {
      return false;
    }
  }

  function read(key, fallback) {
    try {
      const value = localStorage.getItem(key);
      return value ? JSON.parse(value) : fallback;
    } catch (error) {
      return fallback;
    }
  }

  function write(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
      return true;
    } catch (error) {
      console.warn('Local storage quota reached. Falling back to memory.');
      return false;
    }
  }

  return { isAvailable, read, write };
})();
