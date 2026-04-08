const scrl_elements=document.querySelector(".section-scroll");

const obs=new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
        if (entry.isIntersecting) {
            entry.target.classList.add("visible");
            obs.unobserve(entry.target);
        }
    });
}, { threshold: 0.15 }
);

obs.observe(scrl_elements);


