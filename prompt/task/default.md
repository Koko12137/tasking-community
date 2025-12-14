# 任务执行规范协议

## 任务简介

该任务是一个问答任务，通常用于一系列任务的根任务节点。基于该任务，Agent 系统可以衍生出一列子任务。

## 任务状态规范

任务执行过程中，如果需要记录任务的不同状态以支持记忆机制的处理，可以使用以下 XML 片段定义任务状态：

```xml
<state name="STATE 1">
    <description>DESCRIPTION 1</description>
</state>
<state name="STATE 2">
    <description>DESCRIPTION 2</description>
</state>
```

## 任务输入规范

在任务执行过程中，需要输入以下信息，并且需要按照格式进行组织：

```xml
<query>
什么是人工智能？ <!-- IGNORE: 这仅仅是一个输入示范 -->
</query>
```

## 任务输出规范

```xml
<output>
<definition> <!-- IGNORE: 这仅仅是一个输出标签示范 -->
人工智能（Artificial Intelligence，简称 AI）是xxxxx <!-- IGNORE: 这仅仅是一个标签内容示范 -->
</definition>
<references> <!-- IGNORE: 这仅仅是一个输出标签示范 -->
<link>https://example.com/article1</link> <!-- IGNORE: 这仅仅是一个标签内容示范 -->
<link>https://example.com/article2</link> <!-- IGNORE: 这仅仅是一个标签内容示范 -->
</references>
</output>
```

## 注意事项

1. 输入必须按照规范的 XML 格式进行组织，因为系统会基于 XML 结构对任务输入进行解析和处理。
2. xxxx
...
