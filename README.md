# MEDUSA© Platform

MEDUSA© is a software ecosystem for the development of BCIs and neuroscience experiments. It has two independent components with dfferent goals: MEDUSA© Kernel and MEDUSA© Platform. This repository contains MEDUSA© Platform.

MEDUSA© Platform is a desktop application, programmed in Python, which implements high level functionalities to perform BCI and cognitive neuroscience experiments. It includes a modern graphic user interface (GUI) sustained by the advanced signal acquisition functions and real time charts. One of the most critical features is the possibility to install and create apps, which are implementations of neuroscience and BCI experiments or paradigms. Noteworthy, all these functionalities rely on [MEDUSA© Kernel](https://github.com/medusabci/medusa-kernel) to perform the necessary real-time signal processing.

## Information

Check the following links to know more about the MEDUSA environment for neurotechnology and brain-computer interface (BCI) experiments:

- Website: https://www.medusabci.com/
- Documentation: [https://docs.www.medusabci.com/medusa-platform/](https://docs.medusabci.com/platform/v2022/getstarted.php)

Important: MEDUSA Platform is under heavy development! It may change significantly in following versions


## Design principles

MEDUSA© has been designed and developed following three principles: 

- Modularity: MEDUSA© is made of autonomous structures connected by simple communication protocols that allow to update functionalities quickly without interfere with the rest of the parts. In the case of MEDUSA© Kernel, low-level and high-level functions are totally independent so they can be used regardless the case of study in onine and online experiments. In MEDUSA© Platform, this design philosophy allows the creation of new experi mental protocols on demand using structures called apps, which are independent of real-time acquisition and visualization stages.
- Flexibility: MEDUSA© has been specifically designed as a research tool by means of an architecture that allows to make quick experiments with new signal processing methods and feedback paradigms. In addition, we put special emphasis on the documentation and code comments, including examples and tutorials that illustrate the operation of the platform and how to develop new apps. 
- Scalability: MEDUSA© is designed to update its capabilities over time without modifying non-related parts of code thanks using standardized meta-classes, which is especially useful in a research context. This design allows the software to keep up with latest developments in the BCI field, which may include new signal processing algorithms or BCI paradigms.


## Implemented in Python

MEDUSA© has been developed in Python. Currently, this high-level, open-source programming language is one of the most used in both research and industry due to its simplicity and open-source philosophy [14]. In comparison with other languages, such as C, C++ or Java, Python simplifies the development of complex programs at the expense of an affordable reduction in performance [15]. This is especially important in research environments, where flexibility is a key feature as new methods and experiments are constantly developed. In addition, it has a large community that develops a wide range of specific tools and libraries. MEDUSA© exploits the power of packages such as SciPy, Numpy, Scikit-learn or Tensorflow, which are the result of a joint effort to implement state-of-the-art methods for data processing, machine learning and deep learning [14, 15]. This gives MEDUSA© an important advantage over other neurotechnology platforms (e.g., BCI2000, OpenVibe) because it allows to incorporate the latest developments in these areas directly in the workflow of our software.
