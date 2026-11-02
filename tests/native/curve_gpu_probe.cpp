// Standalone Vulkan storage-buffer readback; no engine or window lifecycle.
// Arguments: shader.spv samples.bin parameters.bin output.bin sample_count.
#include <vulkan/vulkan.h>
#include <array>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

static void Check(VkResult result, const char *operation)
{
    if (result != VK_SUCCESS)
        throw std::runtime_error(std::string(operation) + ": " + std::to_string(result));
}

static std::vector<uint32_t> ReadWords(const char *path)
{
    std::ifstream stream(path, std::ios::binary | std::ios::ate);
    if (!stream)
        throw std::runtime_error(std::string("Cannot open ") + path);
    const size_t bytes = static_cast<size_t>(stream.tellg());
    if (bytes == 0 || bytes % sizeof(uint32_t))
        throw std::runtime_error("Input must contain whole 32-bit words");
    std::vector<uint32_t> words(bytes / sizeof(uint32_t));
    stream.seekg(0);
    stream.read(reinterpret_cast<char *>(words.data()), bytes);
    return words;
}

int main(int argc, char **argv)
{
    if (argc != 6) {
        std::cerr << "shader.spv samples.bin parameters.bin output.bin sample_count\n";
        return 2;
    }
    try {
        const auto code = ReadWords(argv[1]);
        const auto samples = ReadWords(argv[2]);
        const auto parameters = ReadWords(argv[3]);
        const uint32_t count = static_cast<uint32_t>(std::stoul(argv[5]));
        VkApplicationInfo app{VK_STRUCTURE_TYPE_APPLICATION_INFO};
        app.pApplicationName = "Infernux curve readback";
        app.apiVersion = VK_API_VERSION_1_2;
        VkInstanceCreateInfo instanceInfo{VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO};
        instanceInfo.pApplicationInfo = &app;
        VkInstance instance;
        Check(vkCreateInstance(&instanceInfo, nullptr, &instance), "vkCreateInstance");
        uint32_t deviceCount = 0;
        Check(vkEnumeratePhysicalDevices(instance, &deviceCount, nullptr), "enumerate devices");
        std::vector<VkPhysicalDevice> physicalDevices(deviceCount);
        Check(vkEnumeratePhysicalDevices(instance, &deviceCount, physicalDevices.data()), "read devices");
        VkPhysicalDevice physical = VK_NULL_HANDLE;
        uint32_t family = 0;
        for (const auto candidate : physicalDevices) {
            uint32_t familyCount = 0;
            vkGetPhysicalDeviceQueueFamilyProperties(candidate, &familyCount, nullptr);
            std::vector<VkQueueFamilyProperties> properties(familyCount);
            vkGetPhysicalDeviceQueueFamilyProperties(candidate, &familyCount, properties.data());
            for (uint32_t i = 0; i < familyCount; ++i) {
                if (properties[i].queueCount && (properties[i].queueFlags & VK_QUEUE_COMPUTE_BIT)) {
                    physical = candidate;
                    family = i;
                    break;
                }
            }
            if (physical)
                break;
        }
        if (!physical)
            throw std::runtime_error("No compute queue is available");
        const float priority = 1.f;
        VkDeviceQueueCreateInfo queueInfo{VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO};
        queueInfo.queueFamilyIndex = family;
        queueInfo.queueCount = 1;
        queueInfo.pQueuePriorities = &priority;
        VkDeviceCreateInfo deviceInfo{VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO};
        deviceInfo.queueCreateInfoCount = 1;
        deviceInfo.pQueueCreateInfos = &queueInfo;
        VkDevice device;
        Check(vkCreateDevice(physical, &deviceInfo, nullptr, &device), "vkCreateDevice");
        VkQueue queue;
        vkGetDeviceQueue(device, family, 0, &queue);
        VkPhysicalDeviceMemoryProperties memoryProperties;
        vkGetPhysicalDeviceMemoryProperties(physical, &memoryProperties);
        const std::array<VkDeviceSize, 3> sizes{
            samples.size() * sizeof(uint32_t), parameters.size() * sizeof(uint32_t), count * sizeof(uint32_t)};
        std::array<VkBuffer, 3> buffers;
        std::array<VkDeviceMemory, 3> memories;
        std::array<void *, 3> mapped;
        for (size_t index = 0; index < buffers.size(); ++index) {
            VkBufferCreateInfo bufferInfo{VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO};
            bufferInfo.size = sizes[index];
            bufferInfo.usage = VK_BUFFER_USAGE_STORAGE_BUFFER_BIT;
            bufferInfo.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
            Check(vkCreateBuffer(device, &bufferInfo, nullptr, &buffers[index]), "vkCreateBuffer");
            VkMemoryRequirements requirements;
            vkGetBufferMemoryRequirements(device, buffers[index], &requirements);
            uint32_t memoryType = UINT32_MAX;
            const auto flags = VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT;
            for (uint32_t i = 0; i < memoryProperties.memoryTypeCount; ++i) {
                if ((requirements.memoryTypeBits & (1u << i)) &&
                    (memoryProperties.memoryTypes[i].propertyFlags & flags) == flags) {
                    memoryType = i;
                    break;
                }
            }
            if (memoryType == UINT32_MAX)
                throw std::runtime_error("No coherent host-visible storage memory");
            VkMemoryAllocateInfo allocation{VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO};
            allocation.allocationSize = requirements.size;
            allocation.memoryTypeIndex = memoryType;
            Check(vkAllocateMemory(device, &allocation, nullptr, &memories[index]), "vkAllocateMemory");
            Check(vkBindBufferMemory(device, buffers[index], memories[index], 0), "vkBindBufferMemory");
            Check(vkMapMemory(device, memories[index], 0, VK_WHOLE_SIZE, 0, &mapped[index]), "vkMapMemory");
        }
        std::memcpy(mapped[0], samples.data(), sizes[0]);
        std::memcpy(mapped[1], parameters.data(), sizes[1]);
        std::memset(mapped[2], 0, sizes[2]);
        std::array<VkDescriptorSetLayoutBinding, 3> bindings{};
        for (uint32_t i = 0; i < bindings.size(); ++i)
            bindings[i] = {i, VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, 1, VK_SHADER_STAGE_COMPUTE_BIT, nullptr};
        VkDescriptorSetLayoutCreateInfo layoutInfo{VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO};
        layoutInfo.bindingCount = static_cast<uint32_t>(bindings.size());
        layoutInfo.pBindings = bindings.data();
        VkDescriptorSetLayout layout;
        Check(vkCreateDescriptorSetLayout(device, &layoutInfo, nullptr, &layout), "create set layout");
        VkDescriptorPoolSize poolSize{VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, 3};
        VkDescriptorPoolCreateInfo poolInfo{VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO};
        poolInfo.maxSets = 1;
        poolInfo.poolSizeCount = 1;
        poolInfo.pPoolSizes = &poolSize;
        VkDescriptorPool pool;
        Check(vkCreateDescriptorPool(device, &poolInfo, nullptr, &pool), "create descriptor pool");
        VkDescriptorSetAllocateInfo setInfo{VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO};
        setInfo.descriptorPool = pool;
        setInfo.descriptorSetCount = 1;
        setInfo.pSetLayouts = &layout;
        VkDescriptorSet descriptors;
        Check(vkAllocateDescriptorSets(device, &setInfo, &descriptors), "allocate descriptors");
        std::array<VkDescriptorBufferInfo, 3> bufferDescriptors{};
        std::array<VkWriteDescriptorSet, 3> writes{};
        for (uint32_t i = 0; i < writes.size(); ++i) {
            bufferDescriptors[i] = {buffers[i], 0, sizes[i]};
            writes[i] = {VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET};
            writes[i].dstSet = descriptors;
            writes[i].dstBinding = i;
            writes[i].descriptorCount = 1;
            writes[i].descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER;
            writes[i].pBufferInfo = &bufferDescriptors[i];
        }
        vkUpdateDescriptorSets(device, static_cast<uint32_t>(writes.size()), writes.data(), 0, nullptr);
        VkShaderModuleCreateInfo shaderInfo{VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO};
        shaderInfo.codeSize = code.size() * sizeof(uint32_t);
        shaderInfo.pCode = code.data();
        VkShaderModule shader;
        Check(vkCreateShaderModule(device, &shaderInfo, nullptr, &shader), "create shader module");
        VkPipelineLayoutCreateInfo pipelineLayoutInfo{VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO};
        pipelineLayoutInfo.setLayoutCount = 1;
        pipelineLayoutInfo.pSetLayouts = &layout;
        VkPipelineLayout pipelineLayout;
        Check(vkCreatePipelineLayout(device, &pipelineLayoutInfo, nullptr, &pipelineLayout), "create pipeline layout");
        VkComputePipelineCreateInfo pipelineInfo{VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO};
        pipelineInfo.layout = pipelineLayout;
        pipelineInfo.stage = {VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO};
        pipelineInfo.stage.stage = VK_SHADER_STAGE_COMPUTE_BIT;
        pipelineInfo.stage.module = shader;
        pipelineInfo.stage.pName = "main";
        VkPipeline pipeline;
        Check(vkCreateComputePipelines(device, VK_NULL_HANDLE, 1, &pipelineInfo, nullptr, &pipeline), "create pipeline");
        VkCommandPoolCreateInfo commandPoolInfo{VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO};
        commandPoolInfo.queueFamilyIndex = family;
        VkCommandPool commandPool;
        Check(vkCreateCommandPool(device, &commandPoolInfo, nullptr, &commandPool), "create command pool");
        VkCommandBufferAllocateInfo commandInfo{VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO};
        commandInfo.commandPool = commandPool;
        commandInfo.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
        commandInfo.commandBufferCount = 1;
        VkCommandBuffer command;
        Check(vkAllocateCommandBuffers(device, &commandInfo, &command), "allocate command buffer");
        VkCommandBufferBeginInfo begin{VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO};
        Check(vkBeginCommandBuffer(command, &begin), "begin commands");
        vkCmdBindPipeline(command, VK_PIPELINE_BIND_POINT_COMPUTE, pipeline);
        vkCmdBindDescriptorSets(command, VK_PIPELINE_BIND_POINT_COMPUTE, pipelineLayout, 0, 1, &descriptors, 0, nullptr);
        vkCmdDispatch(command, (count + 63) / 64, 1, 1);
        VkMemoryBarrier barrier{VK_STRUCTURE_TYPE_MEMORY_BARRIER};
        barrier.srcAccessMask = VK_ACCESS_SHADER_WRITE_BIT;
        barrier.dstAccessMask = VK_ACCESS_HOST_READ_BIT;
        vkCmdPipelineBarrier(command, VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT, VK_PIPELINE_STAGE_HOST_BIT, 0,
                             1, &barrier, 0, nullptr, 0, nullptr);
        Check(vkEndCommandBuffer(command), "end commands");
        VkFenceCreateInfo fenceInfo{VK_STRUCTURE_TYPE_FENCE_CREATE_INFO};
        VkFence fence;
        Check(vkCreateFence(device, &fenceInfo, nullptr, &fence), "create fence");
        VkSubmitInfo submit{VK_STRUCTURE_TYPE_SUBMIT_INFO};
        submit.commandBufferCount = 1;
        submit.pCommandBuffers = &command;
        Check(vkQueueSubmit(queue, 1, &submit, fence), "submit compute");
        Check(vkWaitForFences(device, 1, &fence, VK_TRUE, 30'000'000'000ULL), "wait for compute");
        std::ofstream output(argv[4], std::ios::binary);
        output.write(static_cast<const char *>(mapped[2]), sizes[2]);
        VkPhysicalDeviceProperties properties;
        vkGetPhysicalDeviceProperties(physical, &properties);
        std::cout << properties.deviceName << ": " << count << " samples\n";
        vkDestroyFence(device, fence, nullptr);
        vkDestroyCommandPool(device, commandPool, nullptr);
        vkDestroyPipeline(device, pipeline, nullptr);
        vkDestroyPipelineLayout(device, pipelineLayout, nullptr);
        vkDestroyShaderModule(device, shader, nullptr);
        vkDestroyDescriptorPool(device, pool, nullptr);
        vkDestroyDescriptorSetLayout(device, layout, nullptr);
        for (size_t i = 0; i < buffers.size(); ++i) {
            vkUnmapMemory(device, memories[i]);
            vkDestroyBuffer(device, buffers[i], nullptr);
            vkFreeMemory(device, memories[i], nullptr);
        }
        vkDestroyDevice(device, nullptr);
        vkDestroyInstance(instance, nullptr);
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
