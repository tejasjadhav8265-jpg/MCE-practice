function login() {
  const user = document.getElementById("username").value;

  if (!user) {
    alert("Enter username");
    return;
  }

  window.location.href = "../dashboard/dashboard.html";
}