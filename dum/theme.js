const html=document.querySelector("html");
const btn=document.getElementById("themeToggle");

let cur_thm=localStorage.getItem("theme");
if (cur_thm===null) {
    cur_thm="light";
}

html.setAttribute("data-theme", cur_thm);

if (cur_thm==="dark") {
    btn.setAttribute("aria-pressed", "true");
} else {
    btn.setAttribute("aria-pressed", "false");
}

btn.addEventListener("click", () => {
    if (cur_thm==="dark") {
        cur_thm="light";
    } else {
        cur_thm="dark";
    }

    html.setAttribute("data-theme", cur_thm);
    localStorage.setItem("theme", cur_thm);

    if (cur_thm==="dark") {
        btn.setAttribute("aria-pressed", "true");
    } else {
        btn.setAttribute("aria-pressed", "false");
    }
});



