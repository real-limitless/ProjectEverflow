import { useLocation } from "react-router-dom";
import { useEffect } from "react";
import pageContent from "@/data/pageContent.json";

const NotFound = () => {
  const location = useLocation();

  useEffect(() => {
    console.error(pageContent.errorMessages.pageNotFound, location.pathname);
  }, [location.pathname]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-100">
      <div className="text-center">
        <h1 className="mb-4 text-4xl font-bold">{pageContent.notFound.title}</h1>
        <p className="mb-4 text-xl text-gray-600">{pageContent.notFound.heading}</p>
        <a href={pageContent.notFound.linkUrl} className="text-blue-500 underline hover:text-blue-700">
          {pageContent.notFound.linkText}
        </a>
      </div>
    </div>
  );
};

export default NotFound;
