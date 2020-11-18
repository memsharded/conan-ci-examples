cmake_minimum_required(VERSION 2.8)
project(MyHello CXX)

include(${CMAKE_BINARY_DIR}/conanbuildinfo.cmake)
conan_basic_setup()

add_library(app app.cpp)
target_link_libraries(app PUBLIC ${CONAN_LIBS})
add_executable(main_app main.cpp)
target_link_libraries(main_app PRIVATE app)
